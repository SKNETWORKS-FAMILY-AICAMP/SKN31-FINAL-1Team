#tasks/services.py
import logging
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum

from meetings.models import SpecDocument
from requirements.models import RequirementDefinition, RequirementItem
from tasks.models import TaskAssignment, TaskStatusCode

from task_generation.agent import generate_tasks
from team_sizing import apply_complexity_buffer, build_skill_role_map, estimate_team_size
from work_package import apply_split_decisions, assemble_packages, assert_full_coverage, build_work_packages

from tasks.planning_context import build_employee_profiles, load_known_experience_tags, persist_experience_tags
from project_scale.agent import assess_project_complexity
from assignee_mapping.agent import assignee_mapping_node
from assignee_recommend.agent import assignee_recommend_node
from assignee_recommend.rule_filter import (
    _sane_buffer,
    calculate_max_hours_per_assignee,
    flatten_assignable_units,
    list_project_workdays,
)
from assignment_ranking.agent import decide_package_splits
from assignment_explanation.agent import summarize_plan
from common.models import CommonCode
from shared.llm_client import traceable

# 2026-09-11 (Phase 1): 일정 배치는 tasks.scheduler(결정적 순수 모듈)에 위임한다.
from tasks.scheduler import (
    DEFAULT_RISK_BUFFER,
    FOCUS_HOURS_PER_DAY,
    ScheduleError,
    plan_days,
    schedule,
)

# Phase 0에서 이 모듈에 있던 이름들 — 기존 import(테스트 등)를 깨지 않도록 재노출.
_planned_days = plan_days

logger = logging.getLogger(__name__)
User = get_user_model()

# CommonCode(REQ_PRIORITY).code_name(HIGH/MEDIUM/LOW) -> ai/assignee_recommend가
# 기대하는 표기(High/Medium/Low, rule_filter._PRIORITY_RANK 참고). 대소문자가
# 다르면 우선순위 정렬이 조용히 다 "미지정" 취급되어 순서가 무너진다.
PRIORITY_LABEL_FOR_AI = {"HIGH": "High", "MEDIUM": "Medium", "LOW": "Low"}


def _build_requirement_doc(req_def: RequirementDefinition) -> dict:
    requirements = []
    for item in req_def.items.all():
        priority_name = item.priority_code.code_name if item.priority_code else None
        requirements.append({
            "id": item.req_code,
            "title": item.req_name,
            "description": item.description,
            "priority": PRIORITY_LABEL_FOR_AI.get(priority_name),
        })
    return {"requirements": requirements}


def _build_project_context(req_def: RequirementDefinition) -> dict:
    """
    project_scale.agent.assess_project_complexity()에 넘길 기획서 상위 맥락.
    개별 요구사항 항목이 아니라 SpecDocument(기획서) 단계의 "전체 그림"을 본다 —
    task_generation이 이미 쪼갠 업무 단위 합산(team_sizing.py)만으로는 못 잡는
    신규 기술 도입/외부 연동/미확정 사항 같은 정성적 리스크를 여기서 판단한다.
    """
    spec = req_def.spec
    return {
        "overview": spec.overview or "",
        "problem_definition": spec.problem_definition or "",
        "key_features": spec.key_features or "",
        "tech_stack": spec.tech_stack or "",
        "final_decisions": spec.final_decisions or "",
    }


def _assignee_display_name(user_id):
    """TaskAssignmentSerializer.get_assigned_user_name과 동일한 성+이름 규칙."""
    if user_id is None:
        return None
    u = User.objects.filter(pk=user_id).first()
    if not u:
        return None
    full_name = f"{u.last_name}{u.first_name}".strip()
    return full_name or u.username


def _schedule_suggestion_dates(suggestions: list, start_date: date, end_date: date) -> dict:
    """
    suggestions 각 항목에 suggested_start_date / suggested_end_date /
    exceeds_project_period 를 채우고, 일정 요약(summary) dict를 반환한다.

    2026-09-11 (Phase 1): 실제 배치 계산은 tasks.scheduler.schedule()에 위임한다.
    이 함수는 suggestions <-> scheduler 입출력 형태만 변환한다(정책·알고리즘은
    scheduler.py 한 곳에만 둔다). 의존성(depends_on)은 Phase 2에서 채워지며
    없으면 Phase 0과 동일하게 담당자별 ASAP 연속 배치가 된다.

    반환 summary: {"projected_finish_date": iso|None, "project_buffer_days": int,
                   "exceeds_project_period": bool, "feasible": bool}.
    project_buffer_days는 종료일을 넘기면 음수(초과 일수) — 남는 기간을 가짜
    버퍼로 흡수하지 않고 그대로 노출한다. 의존성 순환이면 ScheduleError.
    """
    workdays = list_project_workdays(start_date, end_date)
    units = [
        {
            "unit_id": s["unit_id"],
            "title": s.get("title"),  # schedule_reason 문구에 쓰임 (Phase 4)
            "assignee_id": s["assignee_id"],
            "estimated_hours": s.get("estimated_hours"),
            "risk_buffer_factor": s.get("risk_buffer_factor"),
            "depends_on": s.get("depends_on") or [],
        }
        for s in suggestions
    ]
    result = schedule(units, workdays)

    for s in suggestions:
        placed = result["units"].get(s["unit_id"], {})
        s["suggested_start_date"] = placed.get("start_date")
        s["suggested_end_date"] = placed.get("end_date")
        s["exceeds_project_period"] = placed.get("exceeds_project_period", False)
        s["schedule_reason"] = placed.get("schedule_reason", "")  # Phase 4

    return result["summary"]


def _recompute_workload_fit_by_schedule(
    suggestions: list, current_workload: dict, total_workdays: int, max_hours_per_assignee: float,
) -> None:
    """
    2026-09-17: workload_fit("이번 배정 포함 현재 부하 …" 서술)는 원래
    assignee_recommend.rule_filter.schedule_assignments()가 담당자를 결정하던
    순서(우선순위+묶음 크기, 날짜와 무관) 그대로 누적 계산해서 만들어진다. 그런데
    PM 미리보기 화면은 같은 담당자의 업무를 캘린더 날짜순으로 나열해서 보여주므로,
    이 두 순서가 어긋나는 조합(우선순위상 먼저 배정 결정된 일이 실제 일정에서는
    나중에 배치되는 경우)에서는 화면에 보이는 순서로 읽었을 때 부하가 거꾸로 가는
    것처럼 보이는 문제가 실측됨(사용자 리포트로 재현 확인).

    _schedule_suggestion_dates()가 suggested_start_date를 다 채운 뒤(=최종 캘린더
    배치가 확정된 뒤) 호출한다 — 담당자 배정 자체는 건드리지 않고, 화면에 보이는
    순서(날짜순) 그대로 담당자별 누적 부하를 다시 계산해 workload_fit 문구만
    덮어쓴다. current_workload 시딩 방식은 schedule_assignments()의 초기화 로직과
    동일하게 맞춘다(기존 업무가 전혀 없는 담당자는 0평일부터, 있으면
    plan_days(기존시간, 기본버퍼)부터 시작).
    """
    by_assignee: dict = {}
    for s in suggestions:
        if s.get("assignee_id") is not None:
            by_assignee.setdefault(s["assignee_id"], []).append(s)

    for assignee_id, items in by_assignee.items():
        items.sort(key=lambda s: s.get("suggested_start_date") or "9999-12-31")
        key = str(assignee_id)
        hours = float(current_workload.get(key, 0.0))
        days = plan_days(hours, DEFAULT_RISK_BUFFER) if key in current_workload else 0
        for s in items:
            buffer = _sane_buffer(s.get("risk_buffer_factor"))
            hours += float(s.get("estimated_hours") or 0)
            days += plan_days(s.get("estimated_hours"), buffer)
            s["workload_fit"] = (
                f"이번 배정 포함 현재 부하 {hours:.1f}시간 · "
                f"약 {days}평일 (프로젝트 {total_workdays}평일, 참고 상한 {max_hours_per_assignee:.1f}시간)"
            )


# 2026-09-11 (Phase 4): 계획 검토 요약(결정적) + LLM 브리핑 컨텍스트.
def _build_plan_review(suggestions: list) -> dict:
    """PM이 확정 전에 손봐야 할 항목만 모은다 — 전부 코드로 집계(LLM 아님)."""
    held = [
        {"unit_id": s["unit_id"], "title": s["title"], "reason": s.get("hold_explanation") or ""}
        for s in suggestions
        if s.get("review_required")
    ]
    over = [
        {"unit_id": s["unit_id"], "title": s["title"], "assignee_name": s.get("assignee_name")}
        for s in suggestions
        if s.get("exceeds_project_period") and s.get("assignee_id") is not None
    ]
    return {"held_units": held, "over_period_units": over, "needs_attention": bool(held or over)}


def _build_briefing_context(
    suggestions: list, schedule_summary: dict, complexity, split_decisions: dict
) -> dict:
    assigned = [s for s in suggestions if s.get("assignee_id") is not None]
    load: dict = {}
    for s in assigned:
        name = s.get("assignee_name") or str(s.get("assignee_id"))
        entry = load.setdefault(name, {"assignee_name": name, "hours": 0.0, "unit_count": 0})
        entry["hours"] += float(s.get("estimated_hours") or 0)
        entry["unit_count"] += 1
    top_load = sorted(load.values(), key=lambda e: -e["hours"])[:5]
    review = _build_plan_review(suggestions)
    return {
        "complexity": (
            {"grade": complexity.complexity.value, "reason": complexity.complexity_reason}
            if complexity is not None else None
        ),
        "schedule": {
            k: schedule_summary.get(k)
            for k in ("projected_finish_date", "project_end_date",
                      "project_buffer_days", "exceeds_project_period")
        },
        "total_units": len(suggestions),
        "assigned_units": len(assigned),
        "held_units": [{"title": h["title"], "reason": h["reason"]} for h in review["held_units"]],
        "over_period_units": [
            {"title": o["title"], "assignee_name": o["assignee_name"]}
            for o in review["over_period_units"]
        ],
        "package_splits": [{"reason": d.get("reason", "")} for d in split_decisions.values()],
        "assignee_load": [
            {**e, "hours": round(e["hours"], 1)} for e in top_load
        ],
    }


@traceable(name="generate_task_suggestions")
def generate_task_suggestions(spec_id: int, on_stage=None) -> dict:
    """
    요구사항정의서 승인 후 PM이 누르는 "업무 배분 실행" — 실제 AI 파이프라인
    (task_generation -> assignee_mapping -> assignee_recommend)을 순서대로
    호출해 PM이 검토/수정할 수 있는 미리보기(suggestions) 목록을 반환한다.

    2026-09-15: 반환과 별개로, 생성 직후 결과를 TaskAssignment에 BACKLOG(초안)
    상태로 바로 저장한다(임시저장) — PM이 확정 전 이탈해도 안 날아간다. 다만
    이건 어디까지나 "안전하게 보관"이지 최종본이 아니다 — PM이 "확정" 버튼을
    눌러 confirm_task_assignments()를 호출하면 이 BACKLOG 행을 지우고 최종
    (편집 반영) 내용으로 PENDING_APPROVAL을 다시 만든다(2단계 확정 플로우).

    on_stage: 있으면 각 단계 시작 시 사람이 읽을 라벨(str)로 호출한다(선택).
    이 파이프라인이 순차 LLM 호출 여러 개(업무 생성→복잡도 판단→패키지 분할→
    담당자 매핑→담당자 추천→브리핑)로 1~수 분 걸리는 게 정상이라("느리다"는
    문의 확인 결과, 2026-09-14), 백그라운드 실행 + 진행 단계 폴링으로 체감을
    개선하기 위해 추가했다 — 이 함수 자체의 로직/순서는 바꾸지 않는다.
    """
    def _stage(label: str) -> None:
        if on_stage:
            on_stage(label)

    try:
        spec = SpecDocument.objects.get(spec_id=spec_id)
    except SpecDocument.DoesNotExist:
        return {"status": "error", "message": "기획서를 찾을 수 없습니다."}

    req_def = RequirementDefinition.objects.filter(spec=spec).order_by('-id').first()
    if not req_def:
        return {"status": "error", "message": "요구사항 정의서가 없습니다."}
    
    # 5단계 Business Validation: 요구사항정의서 승인(APPROVED) 상태 검증
    if req_def.status_code_id != 'APPROVED':
        return {
            "status": "error", 
            "message": f"요구사항 정의서가 승인(APPROVED) 상태가 아닙니다. (현재 상태: {req_def.status_code_id})"
        }

    if not req_def.items.exists():
        return {"status": "error", "message": "요구사항 항목이 없습니다."}

    available_skills = list(
        CommonCode.objects.filter(group__group_code__startswith="SKILL").values_list("code_name", flat=True)
    )
    requirement_doc = _build_requirement_doc(req_def)

    # 2026-09-11(팀 결정): estimated_hours 산정 때 프로젝트 기간을 참고 신호로
    # 주기 위해, 날짜 계산을 업무 생성보다 먼저 한다.
    start_date = req_def.spec.period_start or date.today()
    end_date = req_def.spec.period_end or (start_date + timedelta(days=90))
    project_period = {
        "start_date": str(start_date),
        "end_date": str(end_date),
        "workdays": len(list_project_workdays(start_date, end_date)),
    }

    _stage("업무 생성 중…")
    try:
        task_items = generate_tasks(
            requirement_doc, available_skills=available_skills, project_period=project_period
        )
    except Exception as e:
        logger.exception("업무 생성 실패 (spec_id=%s)", spec_id)
        return {"status": "error", "message": f"업무 생성 실패: {e}"}
    tasks = [t.model_dump(mode="json") for t in task_items]

    # 2026-09-11: 병렬 호출을 시도했다가 되돌렸다 — 이 계정의 OpenAI 분당 토큰
    # 한도(TPM)가 이미 호출 하나로 거의 다 차는 수준이라(단일 호출이 2만 토큰
    # 넘게 요청하는 경우 실측됨), 두 LLM 호출을 동시에 보내면 같은 예산을
    # 두고 서로 부딪혀 429(rate_limit_exceeded)가 오히려 더 빨리·더 자주
    # 났다(실측: 순차 대비 병렬 적용 후 이전보다 이른 단계에서 429 재현).
    # 병목이 "순차 대기시간"이 아니라 "분당 토큰 예산" 자체라 병렬화가
    # 역효과였다 — 순차 호출로 되돌린다.
    _stage("프로젝트 규모 판단 중…")
    project_context = _build_project_context(req_def)
    try:
        complexity = assess_project_complexity(project_context)
    except Exception as e:
        logger.warning("프로젝트 복잡도 판단 실패, 버퍼 없이 진행 (spec_id=%s): %s", spec_id, e)
        complexity = None

    # 2026-09-11: skill->role 매핑을 하드코딩 표 대신 실제 인력에서 도출한다.
    # raw_profiles는 담당자 매핑에도 재사용하므로 여기서 한 번만 조회한다.
    raw_profiles = build_employee_profiles()
    skill_role_map = build_skill_role_map(raw_profiles)
    team_size = estimate_team_size(tasks, start_date, end_date, skill_role_map=skill_role_map)
    if complexity is not None:
        team_size = apply_complexity_buffer(team_size, complexity.complexity.value)

    # 2026-09-11 (Phase 2 item 7 + Phase 3): 배정 단위를 WorkPackage(기능 묶음)로
    # 묶고, LLM(assignment_ranking)이 "한 사람에게 다 맡길지 / 나눌지"만 판단한 뒤
    # 코드가 그 결과대로 하위 패키지로 쪼갠다. 이 package_by_unit을 assignee_recommend에
    # 넘겨 배정을 같은 그룹핑으로 몰아준다. LLM이 실패하면 분할 없이 진행한다.
    flat_units = flatten_assignable_units(tasks)
    unit_lookup = {u["unit_id"]: u for u in flat_units}
    wp = build_work_packages(flat_units)
    try:
        max_hours_per_assignee = calculate_max_hours_per_assignee(str(start_date), str(end_date))
    except ValueError:
        max_hours_per_assignee = 0.0

    _stage("업무 패키지 분할 판단 중…")
    try:
        split_decisions = decide_package_splits(wp["packages"], unit_lookup, max_hours_per_assignee)
    except Exception:
        logger.exception("패키지 분할 판단 중 오류 — 분할 없이 진행 (spec_id=%s)", spec_id)
        split_decisions = {}
    package_by_unit = apply_split_decisions(flat_units, wp["package_by_unit"], split_decisions)
    assert_full_coverage(package_by_unit, flat_units)
    work_packages_view = assemble_packages(flat_units, package_by_unit)

    # 2026-09-11: 패키지 분할 판단과 담당자 매핑을 동시에 돌려봤다가 되돌렸다 —
    # 위 주석(업무 생성/복잡도 판단 근처) 참고, 이 계정 TPM 한도에서는 병렬
    # 호출이 429를 더 빨리·자주 유발해 순차 호출로 되돌렸다.
    _stage("담당자 정보 분석 중…")
    # 2026-09-14: 경력기술서(career_history_text)는 자주 안 바뀌는데 예전엔
    # 이 값을 캐시 시드로 넘긴 적이 없어(assignee_mapping_node 쪽 훅은 있었지만
    # 호출부가 채운 적 없음) 실행할 때마다 매번 LLM으로 다시 태그를 뽑고
    # 있었다 — DB 캐시(EmployeeExperienceTagCache)에서 미리 읽어 시드한다.
    known_experience_tags = load_known_experience_tags(raw_profiles)
    # 2026-09-14: 프로젝트 전체 누적 부하(취소된 업무는 실제 부하가 아니므로 제외) —
    # 원래 A2-3 직전에만 조회했는데, 담당자매핑(A2-2.5)의 역할별 후보 상한
    # (rule_filter.filter_candidates)이 "이 역할 상위 후보들의 남는 가용시간이
    # 부족하면 후보를 더 넣는다" 판단에 이 값을 써야 해서 여기로 당겨왔다.
    workload_qs = (
        TaskAssignment.objects
        .exclude(status_code_id='CANCELLED')
        .values('assigned_user_id')
        .annotate(total=Sum('estimated_hours'))
    )
    current_workload = {str(row['assigned_user_id']): float(row['total'] or 0) for row in workload_qs}
    try:
        mapping_result = assignee_mapping_node({
            "raw_employee_profiles": raw_profiles,
            "tasks": tasks,
            "known_experience_tags": known_experience_tags,
            "current_workload": current_workload,
            "total_workdays": project_period["workdays"],
            "skill_role_map": skill_role_map,
        })
    except Exception as e:
        logger.exception("담당자 매핑 실패 (spec_id=%s)", spec_id)
        return {"status": "error", "message": "담당자 매핑 중 오류가 발생했습니다(AI 서버 요청량 초과일 수 있습니다). 잠시 후 다시 시도해주세요."}
    if mapping_result.get("error"):
        return {"status": "error", "message": f"담당자 매핑 실패: {mapping_result['error']}"}
    member_profiles = mapping_result["member_profiles"]
    if not member_profiles:
        return {"status": "error", "message": "업무에 필요한 스킬을 가진 재직 사원이 없습니다."}
    # 새로 뽑았든 캐시에서 왔든 다시 저장해둔다 — 다음 실행부터 확실히 히트하게.
    persist_experience_tags(raw_profiles, member_profiles)

    _stage("담당자 배정 추천 중…")

    def _on_assignee_progress(event: dict) -> None:
        if event["type"] == "scheduled":
            assignee_ids = sorted({
                s["employee_id"] for s in event["scheduled"] if s["employee_id"] is not None
            })
            names = [n for n in (_assignee_display_name(i) for i in assignee_ids) if n]
            if not names:
                _stage("배정 가능한 담당자가 없어 보류 사유 작성 중…")
                return
            shown = ", ".join(names[:3])
            if len(names) > 3:
                shown += f" 외 {len(names) - 3}명"
            _stage(f"총 {len(names)}명 배정 중 — {shown}")
        elif event["type"] == "reasons_progress":
            _stage(f"배정 사유 작성 중 ({event['done']}/{event['total']}건)")

    try:
        recommend_result = assignee_recommend_node({
            "member_profiles": member_profiles,
            "current_workload": current_workload,
            "project_start_date": str(start_date),
            "project_end_date": str(end_date),
            "tasks": tasks,
            "requirement_doc": requirement_doc,
            "package_by_unit": package_by_unit,  # Phase 3: 분할 반영된 그룹핑
            "on_progress": _on_assignee_progress,
        })
    except Exception as e:
        logger.exception("담당자 추천 실패 (spec_id=%s)", spec_id)
        return {"status": "error", "message": "담당자 추천 중 오류가 발생했습니다(AI 서버 요청량 초과일 수 있습니다). 잠시 후 다시 시도해주세요."}
    if recommend_result.get("error"):
        return {"status": "error", "message": f"담당자 추천 실패: {recommend_result['error']}"}
    assignments = recommend_result["assignments"]

    epic_lookup = {}
    difficulty_lookup = {}
    for t in tasks:
        epic_lookup[t["task_id"]] = (t.get("epic_id", ""), t.get("epic_title", ""))
        difficulty_lookup[t["task_id"]] = t.get("difficulty_reason", "")
        for sub in t.get("subtasks") or []:
            epic_lookup[sub["subtask_id"]] = (t.get("epic_id", ""), t.get("epic_title", ""))
            difficulty_lookup[sub["subtask_id"]] = t.get("difficulty_reason", "")

    suggestions = []
    for a in assignments:
        unit = unit_lookup.get(a["unit_id"])
        if not unit:
            continue

        assignee_id_raw = a.get("employee_id")
        assignee_id = int(assignee_id_raw) if assignee_id_raw is not None else None

        epic_no, epic_title = epic_lookup.get(a["unit_id"], ("", ""))
        reason = a.get("reason") or {}

        suggestions.append({
            "unit_id": a["unit_id"],
            "source_req_id": a["source_req_id"],
            "title": unit["title"],
            "description": unit["description"],
            "estimated_hours": unit["estimated_hours"],
            "difficulty_reason": difficulty_lookup.get(a["unit_id"], ""),
            "epic_no": epic_no,
            "epic_title": epic_title,
            "assignee_id": assignee_id,
            "assignee_name": _assignee_display_name(assignee_id),
            "score": a.get("score"),
            "tech_fit": reason.get("skill_fit"),
            "workload_fit": reason.get("workload"),
            "experience_fit": reason.get("similar_experience"),
            "review_required": a.get("review_required", False),
            "hold_explanation": a.get("hold_explanation"),
            # 2026-09-11 (Phase 2): 일정 스케줄러 입력. flatten_assignable_units가
            # Task 의존성을 unit 단위로 펴서 채운 값을 그대로 넘긴다.
            "depends_on": unit.get("depends_on", []),
            "risk_buffer_factor": unit.get("risk_buffer_factor"),
            "feature_area": unit.get("feature_area"),
            "package_id": package_by_unit.get(a["unit_id"]),  # Phase 2 item 7
            # 2026-09-17: Subtask 단위일 때만 값이 있음(원본 Task의 task_id, 예: "TASK-001").
            # flatten_assignable_units()가 이미 계산해둔 값을 그대로 실어 보낸다 —
            # _persist_assignments()가 TaskAssignment.parent_task(문자열, FK 아님)로 저장한다.
            "parent_task_id": unit.get("parent_task_id"),
            "is_task_header": False,
        })

    # 2026-09-22 (사용자 요청): Subtask로 쪼개진 Task는 flatten_assignable_units가
    # 배정 단위로 안 만들어서(담당자·시간이 Subtask들에 나뉨) 위 루프에 안 걸리고,
    # 그 결과 Task 제목이 어디에도 안 남는 문제가 있었다. 배정 대상은 아니지만
    # Subtask를 묶어 보여주는 표시용 행으로 별도 추가한다 — 담당자/시간은 비워
    # 이중 계산을 피하고, is_task_header로 실제 배정 단위와 구분한다.
    for t in tasks:
        if not t.get("subtasks"):
            continue
        epic_no, epic_title = epic_lookup.get(t["task_id"], ("", ""))
        suggestions.append({
            "unit_id": t["task_id"],
            "source_req_id": t["source_req_id"],
            "title": t["title"],
            "description": t["description"],
            "estimated_hours": sum(sub["estimated_hours"] for sub in t["subtasks"]),
            "difficulty_reason": t.get("difficulty_reason", ""),
            "epic_no": epic_no,
            "epic_title": epic_title,
            "assignee_id": None,
            "assignee_name": None,
            "score": None,
            "tech_fit": None,
            "workload_fit": None,
            "experience_fit": None,
            "review_required": False,
            "hold_explanation": None,
            "depends_on": [],
            "risk_buffer_factor": None,
            "feature_area": t.get("feature_area"),
            "package_id": None,
            "parent_task_id": None,
            "is_task_header": True,
        })

    # 2026-09-11 (Phase 2): LLM이 만든 의존성에 순환이 있으면 여기서 잡힌다.
    try:
        schedule_summary = _schedule_suggestion_dates(suggestions, start_date, end_date)
    except ScheduleError as e:
        logger.warning("업무 일정 계산 실패 (spec_id=%s): %s", spec_id, e)
        return {"status": "error", "message": f"업무 일정 계산 실패: {e}"}

    # 2026-09-17: 최종 캘린더 배치가 확정된 뒤, 화면에 보이는 순서(담당자별 날짜순)
    # 기준으로 workload_fit 문구를 다시 계산한다 — 위 함수 docstring 참고.
    _recompute_workload_fit_by_schedule(
        suggestions, current_workload, project_period["workdays"], max_hours_per_assignee,
    )

    schedule_summary_full = {
        **schedule_summary,
        "project_start_date": str(start_date),
        "project_end_date": str(end_date),
    }

    # 2026-09-15 (임시저장): PM이 검토·확정하기 전 브라우저를 닫거나 며칠 뒤에
    # 돌아와도 이 결과가 안 날아가게, 생성 직후 바로 BACKLOG(초안, "검토 전")
    # 상태로 저장한다. PENDING_APPROVAL(배분승인대기)과는 다른 상태라 — 담당자
    # 개인 업무 목록/대시보드(tasks/views.py, dashboard/views.py)에서 BACKLOG는
    # 제외하므로, PM이 확정하기 전까지 담당자 본인에게도 노출되지 않는다.
    # 같은 요구사항정의서로 재생성하면 이전 BACKLOG 초안만 지우고 새로 쓴다
    # (이미 확정된 PENDING_APPROVAL+ 행은 안 건드림). LLM 파이프라인은 이미
    # 끝났으니, 저장 자체가 실패해도 미리보기 응답은 그대로 돌려준다.
    try:
        with transaction.atomic():
            TaskAssignment.objects.filter(
                req_item__req_def=req_def, status_code_id=TaskStatusCode.BACKLOG,
            ).delete()
            _persist_assignments(req_def, suggestions, TaskStatusCode.BACKLOG)
    except Exception:
        logger.exception("업무 배분 초안 저장 실패 (spec_id=%s) — 미리보기는 그대로 반환", spec_id)

    _stage("계획 요약 작성 중…")
    # 2026-09-11 (Phase 4): 검토 요약(결정적) + LLM 브리핑. 브리핑은 실패해도 계속.
    plan_review = _build_plan_review(suggestions)
    briefing = summarize_plan(
        _build_briefing_context(suggestions, schedule_summary_full, complexity, split_decisions)
    )

    return {
        "status": "success",
        "req_def_id": req_def.id,
        "suggestions": suggestions,
        "team_size_estimate": team_size["team_size_estimate"],
        "complexity_assessment": (
            {"complexity": complexity.complexity.value, "reason": complexity.complexity_reason}
            if complexity is not None else None
        ),
        # 2026-09-10 (Phase 0): 남는 프로젝트 기간을 업무 사이 갭으로 숨기지 않고
        # PM에게 그대로 보여준다. projected_finish_date=마지막 업무 종료일,
        # project_buffer_days=그날부터 프로젝트 종료일까지 남는 평일 수.
        "schedule_summary": schedule_summary_full,
        # 2026-09-11 (Phase 2 item 7 + Phase 3): 기능(WorkPackage) 단위 묶음.
        # LLM 분할 판단이 반영된 최종 그룹핑. PM이 "이 기능은 누가 이어서 맡는지 /
        # 왜 나뉘었는지"를 확인하는 용도. 저장하지 않는 임시 계획 객체.
        "work_packages": work_packages_view,
        "package_splits": [
            {"package_id": pid, "reason": d.get("reason", "")}
            for pid, d in split_decisions.items()
        ],
        # 2026-09-11 (Phase 4): PM이 확정 전 손봐야 할 항목(결정적 집계) + LLM 브리핑.
        "plan_review": plan_review,
        "plan_briefing": {"risks": briefing.risks, "checkpoints": briefing.checkpoints},
    }


def _persist_assignments(req_def: RequirementDefinition, items: list, status_code_id: str) -> int:
    """items를 TaskAssignment로 저장한다. 반환값은 저장된 건수 중 실제 배정
    단위 개수(is_task_header 제외).

    2026-09-15: generate_task_suggestions(초안 자동저장, status=BACKLOG)와
    confirm_task_assignments(확정, status=PENDING_APPROVAL) 둘 다 이 함수를 쓴다 —
    TaskAssignment 생성 로직을 한 곳에만 둔다. items는 suggestions(생성 직후,
    suggested_start_date/suggested_end_date 필드)와 assignments(확정 요청,
    프론트가 start_date/end_date로 보냄) 두 모양을 다 받는다.

    2026-09-22: is_task_header=True인 항목(Subtask로 쪼개진 Task 자신 — 배정
    대상은 아니지만 제목이 사라지지 않도록 표시용으로 저장, 사용자 요청)은
    BACKLOG(미리보기 단계)에서만 저장한다 — PENDING_APPROVAL 이후로 넘어가면
    칸반보드·대시보드·"내 업무" 목록(dashboard/views.py, requirements/views.py
    등, TaskAssignmentListCreateView를 거치지 않고 TaskAssignment를 직접
    쿼리하는 곳이 여럿이라 전부 손보기엔 범위가 큼)에 담당자 없는 구조용 카드로
    섞여 들어갈 위험이 있다. 미리보기 화면(documents/page.tsx) 목적(제목이 안
    사라지게)은 BACKLOG 저장만으로 이미 충분하다.

    2026-09-22 (사용자 요청): is_task_header가 아닌 일반 항목은 assignee_id가
    없어도(미배정/AI 보류 추천) 저장한다 — 예전엔 여기서 건너뛰어서 PM이 확정을
    누르면 미배정 업무가 흔적 없이 사라졌다. 프론트가 확정 전에 "N건 미배정
    상태로 넘어갑니다" 확인을 받으므로, 여기서는 막지 않고 assigned_user_id=NULL로
    저장한다 — 칸반보드/업무 목록이 이미 null 담당자를 안전하게 "미배정"으로
    표시하고 재배정 가능하게 돼 있다(KanbanBoard.tsx, projects/[id]/page.tsx).
    """
    created_count = 0
    for item in items:
        is_header = item.get("is_task_header", False)
        if is_header and status_code_id != TaskStatusCode.BACKLOG:
            continue
        # 2026-09-22 (사용자 요청): 예전엔 담당자 없는 일반 항목을 조용히 건너뛰어서
        # PM이 확정을 누르면 미배정 업무가 아무 흔적 없이 사라졌다 — 프론트가 확정
        # 전에 "N건 미배정 상태로 넘어갑니다" 확인을 받으므로, 여기서는 막지 않고
        # assigned_user_id=NULL로 그대로 저장한다. 칸반보드/업무 목록이 이미 null
        # 담당자를 "미배정"으로 표시하고 재배정 가능하게 돼 있어(KanbanBoard.tsx,
        # projects/[id]/page.tsx) 나중에 거기서 배정하면 된다.

        req_item = req_def.items.filter(req_code=item["source_req_id"]).first()
        if not req_item:
            logger.warning(
                "업무 배정 저장: req_code=%s 매칭 실패로 건너뜀 (req_def_id=%s, status=%s)",
                item.get("source_req_id"), req_def.id, status_code_id,
            )
            continue

        # 2026-09-11 (Phase 4): 프론트가 schedule_reason을 실어 보내면 배정
        # 근거에 함께 저장한다(없으면 무시 — 별도 컬럼은 두지 않음).
        reason_text = " / ".join(filter(None, [
            item.get("tech_fit"), item.get("workload_fit"), item.get("experience_fit"),
            item.get("schedule_reason"),
        ]))

        assignee_id_val = int(item["assignee_id"]) if item.get("assignee_id") is not None else None

        TaskAssignment.objects.create(
            task_no=f"RD{req_def.id}-{item['unit_id']}",
            req_item=req_item,
            assigned_user_id=assignee_id_val,
            project=req_def.project,
            title=item["title"],
            description=item["description"],
            difficulty_reason=item.get("difficulty_reason"),
            estimated_hours=item["estimated_hours"],
            assignment_reason=reason_text,
            # 2026-09-16: 확정(저장) 시점의 담당자·근거를 "AI 원래 추천"으로 그대로 보존해둔다
            # — PM이 나중에 다른 사람으로 재배정했다가 다시 이 사람으로 되돌리면, 재배정
            # API(tasks/serializers.py, tasks/views.py)가 이 값과 비교해 원래 근거를
            # 복원할지 판단한다. Task 헤더 행은 애초에 배정 대상이 아니라 원래 추천
            # 담당자도 없다(None).
            original_assigned_user_id=assignee_id_val if not is_header else None,
            original_assignment_reason=reason_text if not is_header else None,
            # 2026-09-17: Subtask 단위 업무의 원본 Task를 문자열로 기록한다(parent_task는
            # FK가 아니라 CharField — epic_no/epic_title과 같은 패턴). task_no와 같은
            # "RD{req_def.id}-{...}" 형식으로 맞춰, 같은 규칙으로 만들어진 값끼리 비교 가능하게
            # 한다. 2026-09-22부터 부모 Task 자신도 is_task_header=True인 별도 행으로 저장되므로
            # (사용자 요청 — 제목이 완전히 사라지는 문제), 이 값은 그 행을 직접 참조할 수 있다.
            parent_task=(
                f"RD{req_def.id}-{item['parent_task_id']}" if item.get("parent_task_id") else None
            ),
            epic_no=item.get("epic_no", ""),
            epic_title=item.get("epic_title", ""),
            start_date=item.get("start_date") or item.get("suggested_start_date") or None,
            end_date=item.get("end_date") or item.get("suggested_end_date") or None,
            status_code_id=status_code_id,
            is_task_header=is_header,
        )
        # 2026-09-22: created_count는 프론트 확정 토스트("N건")에 그대로 쓰인다
        # (documents/page.tsx) — Task 헤더는 실제 배정 업무가 아니라 표시용이라
        # 이 개수엔 안 넣는다.
        if not is_header:
            created_count += 1
    return created_count


def confirm_task_assignments(req_def_id: int, assignments: list) -> dict:
    """
    PM이 generate_task_suggestions() 결과를 검토/수정한 뒤 "확정"을 눌렀을 때
    호출된다. assignments는 suggestions와 같은 모양이되, assignee_id /
    start_date / end_date는 PM이 편집했을 수 있는 최종 값으로 취급하고 그대로
    신뢰한다(재계산하지 않는다).
    """
    if not any(item.get("assignee_id") is not None for item in assignments):
        return {"status": "error", "message": "담당자가 배정된 업무가 없습니다. 최소 1건 이상 담당자를 지정한 뒤 확정해주세요."}

    try:
        with transaction.atomic():
            # 같은 정의서의 동시 확정을 직렬화한다. 그렇지 않으면 두 요청이 서로의
            # delete/create 사이에 끼어 중복 행 또는 부분 결과를 남길 수 있다.
            req_def = RequirementDefinition.objects.select_for_update().get(pk=req_def_id)
            if req_def.status_code_id != 'APPROVED':
                return {
                    "status": "error",
                    "message": f"요구사항 정의서가 승인(APPROVED) 상태여야 업무를 확정할 수 있습니다. (현재 상태: {req_def.status_code_id})"
                }
            # 2026-09-15: 여기 있던 행은 대부분 generate_task_suggestions()가 이미
            # BACKLOG(초안)로 저장해둔 것들이다 — PM이 확정을 누르면 그 초안을 전부
            # 지우고 최종(편집 반영) 내용으로 PENDING_APPROVAL 다시 만든다. 프론트가
            # 다른 unit_id 조합을 보낼 수도 있어(재생성) delete+recreate를 유지한다.
            TaskAssignment.objects.filter(req_item__req_def=req_def).delete()
            created_count = _persist_assignments(req_def, assignments, TaskStatusCode.PENDING_APPROVAL)
    except RequirementDefinition.DoesNotExist:
        return {"status": "error", "message": "요구사항 정의서를 찾을 수 없습니다."}
    except Exception as e:
        logger.exception("업무 배정 확정 실패 (req_def_id=%s)", req_def_id)
        return {"status": "error", "message": f"업무 배정 확정 중 오류가 발생했습니다: {e}"}

    return {"status": "success", "created_count": created_count}

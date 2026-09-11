#tasks/services.py
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum

from meetings.models import SpecDocument
from requirements.models import RequirementDefinition, RequirementItem
from tasks.models import TaskAssignment

from task_generation.agent import generate_tasks
from team_sizing import apply_complexity_buffer, build_skill_role_map, estimate_team_size
from work_package import apply_split_decisions, assemble_packages, assert_full_coverage, build_work_packages

from tasks.planning_context import build_employee_profiles
from project_scale.agent import assess_project_complexity
from assignee_mapping.agent import assignee_mapping_node
from assignee_recommend.agent import assignee_recommend_node
from assignee_recommend.rule_filter import (
    calculate_max_hours_per_assignee,
    flatten_assignable_units,
    list_project_workdays,
)
from assignment_ranking.agent import decide_package_splits
from assignment_explanation.agent import summarize_plan
from common.models import CommonCode

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


def generate_task_suggestions(spec_id: int) -> dict:
    """
    요구사항정의서 승인 후 PM이 누르는 "업무 배분 실행" — 실제 AI 파이프라인
    (task_generation -> assignee_mapping -> assignee_recommend)을 순서대로
    호출하지만, 여기서는 TaskAssignment를 DB에 저장하지 않고 PM이 검토/수정할
    수 있는 미리보기(suggestions) 목록만 반환한다. 실제 저장은 PM이 "확정" 버튼을
    눌러 confirm_task_assignments()를 호출할 때 이루어진다(2단계 확정 플로우).
    """
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

    # 2026-09-11: 업무 생성(LLM, 가장 무거운 단일 호출)과 복잡도 판단(LLM)은
    # 서로의 결과를 안 쓴다 — complexity는 tasks가 아니라 spec/req_def 필드만
    # 본다. 순차로 하면 둘 다 기다려야 하니 동시에 돌린다(둘 다 I/O 대기라
    # 스레드로 충분 — CPU 작업이 아님).
    project_context = _build_project_context(req_def)
    with ThreadPoolExecutor(max_workers=2) as executor:
        task_future = executor.submit(
            generate_tasks, requirement_doc, available_skills=available_skills, project_period=project_period
        )
        complexity_future = executor.submit(assess_project_complexity, project_context)

        try:
            task_items = task_future.result()
        except Exception as e:
            logger.exception("업무 생성 실패 (spec_id=%s)", spec_id)
            return {"status": "error", "message": f"업무 생성 실패: {e}"}

        try:
            complexity = complexity_future.result()
        except Exception as e:
            logger.warning("프로젝트 복잡도 판단 실패, 버퍼 없이 진행 (spec_id=%s): %s", spec_id, e)
            complexity = None

    tasks = [t.model_dump(mode="json") for t in task_items]

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

    # 2026-09-11: 패키지 분할 판단(LLM)과 담당자 매핑(LLM, 경력 태그 추출)은
    # 둘 다 tasks만 있으면 되고 서로의 결과를 안 기다린다 — 동시에 돌린다.
    with ThreadPoolExecutor(max_workers=2) as executor:
        split_future = executor.submit(
            decide_package_splits, wp["packages"], unit_lookup, max_hours_per_assignee
        )
        mapping_future = executor.submit(
            assignee_mapping_node, {"raw_employee_profiles": raw_profiles, "tasks": tasks}
        )

        try:
            split_decisions = split_future.result()
        except Exception:
            logger.exception("패키지 분할 판단 중 오류 — 분할 없이 진행 (spec_id=%s)", spec_id)
            split_decisions = {}

        try:
            mapping_result = mapping_future.result()
        except Exception as e:
            logger.exception("담당자 매핑 실패 (spec_id=%s)", spec_id)
            return {"status": "error", "message": "담당자 매핑 중 오류가 발생했습니다(AI 서버 요청량 초과일 수 있습니다). 잠시 후 다시 시도해주세요."}

    package_by_unit = apply_split_decisions(flat_units, wp["package_by_unit"], split_decisions)
    assert_full_coverage(package_by_unit, flat_units)
    work_packages_view = assemble_packages(flat_units, package_by_unit)

    if mapping_result.get("error"):
        return {"status": "error", "message": f"담당자 매핑 실패: {mapping_result['error']}"}
    member_profiles = mapping_result["member_profiles"]
    if not member_profiles:
        return {"status": "error", "message": "업무에 필요한 스킬을 가진 재직 사원이 없습니다."}

    # 프로젝트 전체 누적 부하 — 취소된 업무는 실제 부하가 아니므로 제외.
    workload_qs = (
        TaskAssignment.objects
        .exclude(status_code_id='CANCELLED')
        .values('assigned_user_id')
        .annotate(total=Sum('estimated_hours'))
    )
    current_workload = {str(row['assigned_user_id']): float(row['total'] or 0) for row in workload_qs}

    try:
        recommend_result = assignee_recommend_node({
            "member_profiles": member_profiles,
            "current_workload": current_workload,
            "project_start_date": str(start_date),
            "project_end_date": str(end_date),
            "tasks": tasks,
            "requirement_doc": requirement_doc,
            "package_by_unit": package_by_unit,  # Phase 3: 분할 반영된 그룹핑
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
        })

    # 2026-09-11 (Phase 2): LLM이 만든 의존성에 순환이 있으면 여기서 잡힌다.
    try:
        schedule_summary = _schedule_suggestion_dates(suggestions, start_date, end_date)
    except ScheduleError as e:
        logger.warning("업무 일정 계산 실패 (spec_id=%s): %s", spec_id, e)
        return {"status": "error", "message": f"업무 일정 계산 실패: {e}"}

    schedule_summary_full = {
        **schedule_summary,
        "project_start_date": str(start_date),
        "project_end_date": str(end_date),
    }

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


def confirm_task_assignments(req_def_id: int, assignments: list) -> dict:
    """
    PM이 generate_task_suggestions() 결과를 검토/수정한 뒤 "확정"을 눌렀을 때
    호출된다. assignments는 suggestions와 같은 모양이되, assignee_id /
    start_date / end_date는 PM이 편집했을 수 있는 최종 값으로 취급하고 그대로
    신뢰한다(재계산하지 않는다).
    """
    try:
        req_def = RequirementDefinition.objects.get(pk=req_def_id)
    except RequirementDefinition.DoesNotExist:
        return {"status": "error", "message": "요구사항 정의서를 찾을 수 없습니다."}

    # 5단계 Business Validation: 요구사항정의서 승인(APPROVED) 상태 검증
    if req_def.status_code_id != 'APPROVED':
        return {
            "status": "error", 
            "message": f"요구사항 정의서가 승인(APPROVED) 상태여야 업무를 확정할 수 있습니다. (현재 상태: {req_def.status_code_id})"
        }

    if not any(item.get("assignee_id") is not None for item in assignments):
        return {"status": "error", "message": "담당자가 배정된 업무가 없습니다. 최소 1건 이상 담당자를 지정한 뒤 확정해주세요."}

    try:
        with transaction.atomic():
            TaskAssignment.objects.filter(req_item__req_def=req_def).delete()

            created_count = 0
            skipped_no_match = []
            for item in assignments:
                if item.get("assignee_id") is None:
                    continue

                req_item = req_def.items.filter(req_code=item["source_req_id"]).first()
                if not req_item:
                    skipped_no_match.append(item.get("source_req_id"))
                    logger.warning(
                        "업무 배정 확정: req_code=%s 매칭 실패로 건너뜀 (req_def_id=%s)",
                        item.get("source_req_id"), req_def_id,
                    )
                    continue

                # 2026-09-11 (Phase 4): 프론트가 schedule_reason을 실어 보내면 배정
                # 근거에 함께 저장한다(없으면 무시 — 별도 컬럼은 두지 않음).
                reason_text = " / ".join(filter(None, [
                    item.get("tech_fit"), item.get("workload_fit"), item.get("experience_fit"),
                    item.get("schedule_reason"),
                ]))

                TaskAssignment.objects.create(
                    task_no=f"RD{req_def.id}-{item['unit_id']}",
                    req_item=req_item,
                    assigned_user_id=int(item["assignee_id"]),
                    project=req_def.project,
                    title=item["title"],
                    description=item["description"],
                    difficulty_reason=item.get("difficulty_reason"),
                    estimated_hours=item["estimated_hours"],
                    assignment_reason=reason_text,
                    epic_no=item.get("epic_no", ""),
                    epic_title=item.get("epic_title", ""),
                    start_date=item.get("start_date") or None,
                    end_date=item.get("end_date") or None,
                    status_code_id='APPROVED',
                )
                created_count += 1
    except RequirementDefinition.DoesNotExist:
        return {"status": "error", "message": "요구사항 정의서를 찾을 수 없습니다."}
    except Exception as e:
        logger.exception("업무 배정 확정 실패 (req_def_id=%s)", req_def_id)
        return {"status": "error", "message": f"업무 배정 확정 중 오류가 발생했습니다: {e}"}

    return {"status": "success", "created_count": created_count}


# ==========================================
# 뷰(views.py)에서 호출하는 AI 연동 서비스 함수들
# ==========================================

def run_assignee_mapping(data):
    spec_id = data.get("spec_id")
    if not spec_id:
        return {"status": "error", "message": "spec_id는 필수입니다."}
    return generate_task_suggestions(spec_id)


def run_task_generation(data):
    spec_id = data.get("spec_id")
    if not spec_id:
        return {"status": "error", "message": "spec_id는 필수입니다."}
    return generate_task_suggestions(spec_id)
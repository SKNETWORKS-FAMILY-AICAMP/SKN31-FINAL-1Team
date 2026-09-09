#tasks/services.py
import logging
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum

from meetings.models import SpecDocument
from requirements.models import RequirementDefinition, RequirementItem
from tasks.models import TaskAssignment

from task_generation.agent import generate_tasks
from team_sizing import apply_complexity_buffer, estimate_team_size
from project_scale.agent import assess_project_complexity
from assignee_mapping.agent import assignee_mapping_node
from assignee_recommend.agent import assignee_recommend_node
from assignee_recommend.rule_filter import flatten_assignable_units, list_project_workdays
from common.models import CommonCode

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


def _build_employee_profiles() -> list:
    """User + UserSkill + UserCertification -> RawEmployeeProfile 원본 그대로.
    필터링(재직 여부/직무/스킬)은 여기서 하지 않는다 — assignee_mapping의
    rule_filter.filter_candidates()가 코드로 직접 거른다(ai/ 설계 문서 참고)."""
    users = User.objects.all().select_related('job_role_code', 'status_code').prefetch_related(
        'skills__skill_code', 'certifications__cert_code'
    )
    profiles = []
    for u in users:
        profiles.append({
            "employee_id": str(u.id),
            "employee_no": u.emp_no or str(u.id),
            "name": u.get_full_name() or u.username,
            "job_role": u.job_role_code_id or "",
            "is_active": (u.status_code_id == "ACTIVE") and not u.resign_date,
            "skills": [s.skill_code.code_name for s in u.skills.all()],
            "certifications": [c.cert_code.code_name for c in u.certifications.all()],
            "career_history_text": u.past_projects or "",
        })
    return profiles


def _assignee_display_name(user_id):
    """TaskAssignmentSerializer.get_assigned_user_name과 동일한 성+이름 규칙."""
    if user_id is None:
        return None
    u = User.objects.filter(pk=user_id).first()
    if not u:
        return None
    full_name = f"{u.last_name}{u.first_name}".strip()
    return full_name or u.username


def _schedule_suggestion_dates(suggestions: list, start_date: date, end_date: date) -> None:
    """
    assignee_id별로 업무를 프로젝트 기간(평일만) 안에 배치한다. 하루 8시간
    기준, 최소 1일.

    이전엔 프로젝트 시작일부터 쉬지 않고 몰아서 채우기만 해서, 배정된 시간이
    적으면 프로젝트 기간이 한참 남았는데도 일찍 끝나버리는 문제가 있었다
    (2026-09-09 확인 — 21일짜리 프로젝트인데 실제 일정은 3일 만에 끝나버림).
    또한 달력 일수를 그대로 더해서 주말도 업무일로 계산하는 모순도 있었다.

    규칙(같은 담당자의 업무가 여러 건이면 원래 순서 유지):
      - 업무가 2건 이상: 첫 업무=프로젝트 첫 평일, 마지막 업무=프로젝트 마지막
        평일에 정확히 맞추고, 남는 여유는 업무 사이사이에 균등하게 끼워 넣는다.
        → 시작일이 늦춰지지 않으면서도 마지막 업무가 프로젝트 종료일과 일치한다.
      - 업무가 1건뿐: "시작일=프로젝트 시작"과 "종료일=프로젝트 종료"를 동시에
        만족시킬 수 없다(둘 사이 빈 기간을 앞/뒤 어느 한쪽에 둬야 함) — 마지막
        업무가 프로젝트 종료일과 맞아야 한다는 요건을 우선해, 종료일에 맞추고
        시작일을 그만큼 늦춘다.
      - 어느 쪽이든 이 사람의 총 소요일이 프로젝트 평일 수를 넘으면(상한 초과 —
        원래 스케줄러가 막아주지만 방어적으로) exceeds_project_period=True로
        표시하고 자르지 않는다 — 강제로 줄이지 않고 PM이 볼 신호로만 남긴다.

    AI가 아닌 결정적 휴리스틱(assignee_recommend는 날짜를 계산하지 않는다 —
    schemas.AssignmentResult에 날짜 필드 없음). "평일이 뭔지"의 판정 기준은
    ai/assignee_recommend/rule_filter.py의 list_project_workdays() 하나로
    통일한다 — calculate_max_hours_per_assignee()(상한 계산)와 어긋나지 않게.
    """
    workdays = list_project_workdays(start_date, end_date)
    total_workdays = len(workdays)

    by_assignee: dict = {}
    for s in suggestions:
        if s["assignee_id"] is None:
            s["suggested_start_date"] = None
            s["suggested_end_date"] = None
            continue
        by_assignee.setdefault(s["assignee_id"], []).append(s)

    # 프로젝트 기간에 평일이 하루도 없으면(주말만 있거나 종료일이 시작일보다 이른
    # 잘못된 입력) workdays가 빈 리스트라 아래 인덱싱이 전부 IndexError로 죽는다 —
    # 날짜를 배정할 기준 자체가 없으므로 전부 초과로 표시하고 날짜는 비워둔다.
    if total_workdays == 0:
        for items in by_assignee.values():
            for item in items:
                item["exceeds_project_period"] = True
                item["suggested_start_date"] = None
                item["suggested_end_date"] = None
        return

    for items in by_assignee.values():
        n = len(items)
        days_needed = [max(1, round((it["estimated_hours"] or 0) / 8)) for it in items]
        total_real_days = sum(days_needed)
        idle_total = max(0, total_workdays - total_real_days)

        if n == 1:
            end_idx = total_workdays - 1
            start_idx = end_idx - days_needed[0] + 1
            items[0]["exceeds_project_period"] = start_idx < 0
            start_idx = max(0, start_idx)
            items[0]["suggested_start_date"] = workdays[start_idx].isoformat()
            items[0]["suggested_end_date"] = workdays[end_idx].isoformat()
            continue

        # n >= 2: 첫 업무=프로젝트 시작, 마지막 업무=프로젝트 종료, 여유는
        # 업무 사이(내부 gap)에만 균등 분산 — 나머지(remainder)는 마지막 gap에 몰아준다.
        gap_each = idle_total // (n - 1)
        leftover = idle_total - gap_each * (n - 1)

        cursor_idx = 0
        for idx, (item, d) in enumerate(zip(items, days_needed)):
            if idx > 0:
                gap = gap_each + (leftover if idx == n - 1 else 0)
                cursor_idx += gap
            # 이 담당자의 총 소요일이 프로젝트 평일 수를 넘으면(위 idle_total=0인
            # 경우) cursor_idx가 total_workdays를 넘어설 수 있다 — end_idx는 이미
            # 클램프하고 있었지만 start_idx는 안 하고 있어서, 그다음 업무의
            # start_idx가 workdays 범위를 벗어나 IndexError로 죽는 사고가 실제로
            # 재현됐다(담당자 1명에게 프로젝트 평일 수보다 많은 업무를 몰아준 경우).
            # exceeds_project_period=True로 표시하는 건 그대로 두되, 조회용
            # 인덱스는 마지막 평일로 고정해 죽지 않게 한다.
            start_idx = min(cursor_idx, total_workdays - 1)
            end_idx = start_idx + d - 1
            item["exceeds_project_period"] = end_idx > total_workdays - 1
            end_idx = min(end_idx, total_workdays - 1)
            item["suggested_start_date"] = workdays[start_idx].isoformat()
            item["suggested_end_date"] = workdays[end_idx].isoformat()
            cursor_idx = end_idx + 1


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

    try:
        task_items = generate_tasks(requirement_doc, available_skills=available_skills)
    except Exception as e:
        logger.exception("업무 생성 실패 (spec_id=%s)", spec_id)
        return {"status": "error", "message": f"업무 생성 실패: {e}"}
    tasks = [t.model_dump(mode="json") for t in task_items]

    start_date = req_def.spec.period_start or date.today()
    end_date = req_def.spec.period_end or (start_date + timedelta(days=90))

    project_context = _build_project_context(req_def)
    try:
        complexity = assess_project_complexity(project_context)
    except Exception as e:
        logger.warning("프로젝트 복잡도 판단 실패, 버퍼 없이 진행 (spec_id=%s): %s", spec_id, e)
        complexity = None

    team_size = estimate_team_size(tasks, start_date, end_date)
    if complexity is not None:
        team_size = apply_complexity_buffer(team_size, complexity.complexity.value)
    needed_roles = [r["role"] for r in team_size["team_size_estimate"]["by_role"]]

    raw_profiles = _build_employee_profiles()
    try:
        mapping_result = assignee_mapping_node({
            "raw_employee_profiles": raw_profiles,
            "tasks": tasks,
            "needed_roles": needed_roles,
        })
    except Exception as e:
        logger.exception("담당자 매핑 실패 (spec_id=%s)", spec_id)
        return {"status": "error", "message": "담당자 매핑 중 오류가 발생했습니다(AI 서버 요청량 초과일 수 있습니다). 잠시 후 다시 시도해주세요."}
    if mapping_result.get("error"):
        return {"status": "error", "message": f"담당자 매핑 실패: {mapping_result['error']}"}
    member_profiles = mapping_result["member_profiles"]
    if not member_profiles:
        return {"status": "error", "message": "조건에 맞는 담당자 후보가 없습니다(직무/스킬 불일치)."}

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
        })
    except Exception as e:
        logger.exception("담당자 추천 실패 (spec_id=%s)", spec_id)
        return {"status": "error", "message": "담당자 추천 중 오류가 발생했습니다(AI 서버 요청량 초과일 수 있습니다). 잠시 후 다시 시도해주세요."}
    if recommend_result.get("error"):
        return {"status": "error", "message": f"담당자 추천 실패: {recommend_result['error']}"}
    assignments = recommend_result["assignments"]

    unit_lookup = {u["unit_id"]: u for u in flatten_assignable_units(tasks)}
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
        })

    _schedule_suggestion_dates(suggestions, start_date, end_date)

    return {
        "status": "success",
        "req_def_id": req_def.id,
        "suggestions": suggestions,
        "team_size_estimate": team_size["team_size_estimate"],
        "complexity_assessment": (
            {"complexity": complexity.complexity.value, "reason": complexity.complexity_reason}
            if complexity is not None else None
        ),
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

                reason_text = " / ".join(filter(None, [
                    item.get("tech_fit"), item.get("workload_fit"), item.get("experience_fit"),
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
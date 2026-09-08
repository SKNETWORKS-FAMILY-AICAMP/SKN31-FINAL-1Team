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
from team_sizing import estimate_team_size
from assignee_mapping.agent import assignee_mapping_node
from assignee_recommend.agent import assignee_recommend_node
from assignee_recommend.rule_filter import flatten_assignable_units

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


def _schedule_suggestion_dates(suggestions: list, start_date: date) -> None:
    """assignee_id별로 순서대로(같은 순서 유지) 이어붙여 시작/종료일을 매긴다.
    하루 8시간 기준, 최소 1일. AI가 아닌 결정적 휴리스틱(assignee_recommend는
    날짜를 계산하지 않는다 — schemas.AssignmentResult에 날짜 필드 없음)."""
    next_start = {}
    for s in suggestions:
        assignee_id = s["assignee_id"]
        if assignee_id is None:
            s["suggested_start_date"] = None
            s["suggested_end_date"] = None
            continue
        cursor = next_start.get(assignee_id, start_date)
        duration_days = max(1, round((s["estimated_hours"] or 0) / 8))
        unit_start = cursor
        unit_end = cursor + timedelta(days=duration_days - 1)
        s["suggested_start_date"] = unit_start.isoformat()
        s["suggested_end_date"] = unit_end.isoformat()
        next_start[assignee_id] = unit_end + timedelta(days=1)


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
    if not req_def.items.exists():
        return {"status": "error", "message": "요구사항 항목이 없습니다."}

    requirement_doc = _build_requirement_doc(req_def)

    try:
        task_items = generate_tasks(requirement_doc)
    except Exception as e:
        logger.exception("업무 생성 실패 (spec_id=%s)", spec_id)
        return {"status": "error", "message": f"업무 생성 실패: {e}"}
    tasks = [t.model_dump(mode="json") for t in task_items]

    start_date = req_def.spec.period_start or date.today()
    end_date = req_def.spec.period_end or (start_date + timedelta(days=90))

    team_size = estimate_team_size(tasks, start_date, end_date)
    needed_roles = [r["role"] for r in team_size["team_size_estimate"]["by_role"]]

    raw_profiles = _build_employee_profiles()
    mapping_result = assignee_mapping_node({
        "raw_employee_profiles": raw_profiles,
        "tasks": tasks,
        "needed_roles": needed_roles,
    })
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

    recommend_result = assignee_recommend_node({
        "member_profiles": member_profiles,
        "current_workload": current_workload,
        "project_start_date": str(start_date),
        "project_end_date": str(end_date),
        "tasks": tasks,
        "requirement_doc": requirement_doc,
    })
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

    # 여기서는 DB에 아무것도 저장하지 않는다 — task_no 접두어(RD{req_def.id}-)
    # 부여 및 실제 TaskAssignment 생성은 PM이 "확정"을 누른 뒤 confirm_task_assignments()
    # 에서 이루어진다(예전 run_task_generation_pipeline이 여기서 바로 저장하던 부분).
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

    _schedule_suggestion_dates(suggestions, start_date)

    return {
        "status": "success",
        "req_def_id": req_def.id,
        "suggestions": suggestions,
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

    try:
        with transaction.atomic():
            # task_no는 DB에서 unique 제약이 있는데, AI는 매번 실행마다 TASK-001부터
            # 다시 번호를 매긴다 — 그대로 쓰면 다른 요구사항정의서의 이전 실행 결과와
            # 번호가 겹쳐서 IntegrityError가 난다(직접 재현해서 확인). req_def.id를
            # 붙여 전역에서 유일하게 만들고, 같은 요구사항정의서를 재확정한 경우는
            # 기존 배정을 지우고 새로 만든다 — 중복이 아니라 "다시 배분"이 맞는 의미이므로.
            TaskAssignment.objects.filter(req_item__req_def=req_def).delete()

            created_count = 0
            for item in assignments:
                if item.get("assignee_id") is None:
                    continue

                req_item = req_def.items.filter(req_code=item["source_req_id"]).first()
                if not req_item:
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
                    status_code_id='PENDING_APPROVAL',
                )
                created_count += 1
    except RequirementDefinition.DoesNotExist:
        return {"status": "error", "message": "요구사항 정의서를 찾을 수 없습니다."}
    except Exception as e:
        logger.exception("업무 배정 확정 실패 (req_def_id=%s)", req_def_id)
        return {"status": "error", "message": f"업무 배정 확정 중 오류가 발생했습니다: {e}"}

    return {"status": "success", "created_count": created_count}


# ==========================================
# 뷰(views.py)에서 호출하는 AI 연동 서비스 함수들 — 둘 다 같은 파이프라인을 탄다.
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

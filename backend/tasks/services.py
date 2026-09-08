#tasks/services.py
import logging
from datetime import date, timedelta

from django.contrib.auth import get_user_model
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


def run_task_generation_pipeline(spec_id: int) -> dict:
    """
    요구사항정의서 승인 후 PM이 누르는 "업무 배분 실행" — 실제 AI 파이프라인
    (task_generation -> assignee_mapping -> assignee_recommend)을 순서대로
    호출해 TaskAssignment 행까지 만든다.

    이 세 모듈은 backend와 별개인 ai/ 아래에 이미 구현되어 있었는데(2026-09-08
    확인), 지금까지 이 서비스 함수(예전 create_task_assignments_for_spec)는
    실제로는 하나도 호출하지 않고 가짜 샘플 업무 3개만 순환 배정하는 껍데기였다.
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

    # task_no는 DB에서 unique 제약이 있는데, AI는 매번 실행마다 TASK-001부터 다시
    # 번호를 매긴다(_renumber 참고) — 그대로 쓰면 다른 요구사항정의서의 이전 실행
    # 결과와 번호가 겹쳐서 IntegrityError가 난다(직접 재현해서 확인). req_def.id를
    # 붙여 전역에서 유일하게 만들고, 같은 요구사항정의서를 재실행한 경우(재배분)는
    # 기존 배정을 지우고 새로 만든다 — 중복이 아니라 "다시 배분"이 맞는 의미이므로.
    TaskAssignment.objects.filter(req_item__req_def=req_def).delete()

    created = []
    held = []
    for a in assignments:
        unit = unit_lookup.get(a["unit_id"])
        if not unit:
            continue
        if a.get("employee_id") is None:
            held.append({
                "unit_id": a["unit_id"],
                "title": unit["title"],
                "reason": a.get("hold_explanation"),
            })
            continue

        req_item = req_def.items.filter(req_code=a["source_req_id"]).first()
        if not req_item:
            continue

        epic_no, epic_title = epic_lookup.get(a["unit_id"], ("", ""))
        reason = a.get("reason") or {}
        reason_text = " / ".join(filter(None, [
            reason.get("skill_fit"), reason.get("workload"), reason.get("similar_experience"),
        ]))

        assignment = TaskAssignment.objects.create(
            task_no=f"RD{req_def.id}-{a['unit_id']}",
            req_item=req_item,
            assigned_user_id=int(a["employee_id"]),
            project=req_def.project,
            title=unit["title"],
            description=unit["description"],
            difficulty_reason=difficulty_lookup.get(a["unit_id"], ""),
            estimated_hours=unit["estimated_hours"],
            assignment_reason=reason_text,
            epic_no=epic_no,
            epic_title=epic_title,
            status_code_id='PENDING_APPROVAL',
        )
        created.append(assignment)

    return {
        "status": "success",
        "created_count": len(created),
        "held_count": len(held),
        "held": held,
    }


# ==========================================
# 뷰(views.py)에서 호출하는 AI 연동 서비스 함수들 — 둘 다 같은 파이프라인을 탄다.
# ==========================================

def run_assignee_mapping(data):
    spec_id = data.get("spec_id")
    if not spec_id:
        return {"status": "error", "message": "spec_id는 필수입니다."}
    return run_task_generation_pipeline(spec_id)


def run_task_generation(data):
    spec_id = data.get("spec_id")
    if not spec_id:
        return {"status": "error", "message": "spec_id는 필수입니다."}
    return run_task_generation_pipeline(spec_id)

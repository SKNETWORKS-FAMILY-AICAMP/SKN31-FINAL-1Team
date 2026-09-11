# tasks/planning_context.py
"""
2026-09-11 (Phase 3 item 9): 업무 배분 파이프라인이 ai/ 로 넘길 컨텍스트(사원
프로필, 프로젝트 기간)를 한 곳에서 조립한다. DB를 읽어 평범한 dict만 만들고
판단은 하지 않는다 ("코드가 결정, LLM은 판단 입력만" — team_sizing / work_package
와 같은 성격).

기존 services._build_employee_profiles를 여기로 옮기면서 UserSkill.proficiency_level
(숙련도 1~5)을 함께 싣는다 — A2-3 _fit_score가 스킬 매칭 점수를 숙련도로 가중한다.
"""

from datetime import date
from typing import List, Optional, Union

from django.contrib.auth import get_user_model

from assignee_recommend.rule_filter import list_project_workdays

User = get_user_model()


def build_employee_profiles() -> List[dict]:
    """User + UserSkill(+숙련도) + UserCertification -> RawEmployeeProfile 원본 목록.

    필터링(재직 여부/직무/스킬)은 하지 않는다 — assignee_mapping.rule_filter의
    filter_candidates()가 코드로 직접 거른다(ai/ 설계 문서, 2026-09-02 결정).
    """
    users = (
        User.objects.all()
        .select_related("job_role_code", "status_code")
        .prefetch_related("skills__skill_code", "certifications__cert_code")
    )
    profiles: List[dict] = []
    for u in users:
        skill_levels = {
            s.skill_code.code_name: s.proficiency_level
            for s in u.skills.all()
            if s.skill_code
        }
        profiles.append(
            {
                "employee_id": str(u.id),
                "employee_no": u.emp_no or str(u.id),
                "name": u.get_full_name() or u.username,
                "job_role": u.job_role_code_id or "",
                "is_active": (u.status_code_id == "ACTIVE") and not u.resign_date,
                "skills": list(skill_levels.keys()),
                "skill_levels": skill_levels,  # 2026-09-11 (Phase 3): 숙련도(1~5)
                "certifications": [
                    c.cert_code.code_name for c in u.certifications.all() if c.cert_code
                ],
                "career_history_text": u.past_projects or "",
            }
        )
    return profiles


def build_project_context(
    start_date: Union[str, date], end_date: Union[str, date]
) -> dict:
    """프로젝트 기간 컨텍스트 — 시작/종료일과 그 사이 실제 평일 목록.
    일정 스케줄러가 쓰는 '평일' 기준(list_project_workdays)과 한 곳에서 맞춘다."""
    workdays = list_project_workdays(start_date, end_date)
    return {
        "start_date": str(start_date),
        "end_date": str(end_date),
        "workdays": [d.isoformat() for d in workdays],
        "total_workdays": len(workdays),
    }

# tasks/planning_context.py
"""
2026-09-11 (Phase 3 item 9): 업무 배분 파이프라인이 ai/ 로 넘길 컨텍스트(사원
프로필, 프로젝트 기간)를 한 곳에서 조립한다. DB를 읽어 평범한 dict만 만들고
판단은 하지 않는다 ("코드가 결정, LLM은 판단 입력만" — team_sizing / work_package
와 같은 성격).

기존 services._build_employee_profiles를 여기로 옮기면서 UserSkill.proficiency_level
(숙련도 1~5)을 함께 싣는다 — A2-3 _fit_score가 스킬 매칭 점수를 숙련도로 가중한다.
"""

import hashlib
from datetime import date
from typing import Dict, List, Optional, Union

from django.contrib.auth import get_user_model

from assignee_recommend.rule_filter import list_project_workdays
from tasks.models import EmployeeExperienceTagCache

User = get_user_model()


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_known_experience_tags(raw_profiles: List[dict]) -> Dict[str, List[str]]:
    """
    이번 파이프라인에 등장하는 사원들의 career_history_text 중 이미 캐시된
    태그가 있으면 {원문: 태그목록}으로 돌려준다. assignee_mapping_node의
    known_experience_tags로 그대로 넘기면, 원문이 안 바뀐 사람은 LLM을
    다시 부르지 않는다(2026-09-14 도입 — "매번 다시 추출하냐"는 지적 확인
    결과, 캐시 시드 훅은 있었는데 백엔드가 채워 넘긴 적이 없었다).
    """
    texts = {p["career_history_text"].strip() for p in raw_profiles if p.get("career_history_text", "").strip()}
    if not texts:
        return {}
    hash_to_text = {_text_hash(t): t for t in texts}
    rows = EmployeeExperienceTagCache.objects.filter(text_hash__in=hash_to_text.keys())
    return {hash_to_text[row.text_hash]: row.tags for row in rows}


def persist_experience_tags(raw_profiles: List[dict], member_profiles: List[dict]) -> None:
    """
    assignee_mapping_node가 이번에 새로 뽑았든 캐시에서 가져왔든, member_profiles에
    실려 나온 태그를 전부 다시 저장해둔다(이미 캐시된 것도 갱신 시각만 새로 찍히고
    내용은 그대로라 손해가 없다) — 다음 실행부터 load_known_experience_tags가
    바로 히트하게 하기 위함.
    """
    raw_by_id = {p["employee_id"]: p for p in raw_profiles}
    for mp in member_profiles:
        raw = raw_by_id.get(mp.get("employee_id"))
        text = (raw or {}).get("career_history_text", "").strip()
        if not text:
            continue
        EmployeeExperienceTagCache.objects.update_or_create(
            text_hash=_text_hash(text),
            defaults={"tags": mp.get("past_similar_tasks") or []},
        )


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

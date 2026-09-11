"""
assignee_mapping/rule_filter.py

담당자매핑 에이전트는 사원 1인당 LLM을 한 번씩 호출한다. 대상이 많아질수록
호출 횟수·대기시간이 그대로 늘어나므로, LLM을 부르기 전에 후보를 코드로
먼저 추려낸다. 이 필터링은 전부 이미 구조화된 값(직무 코드, 재직 상태, 스킬)만
보고 판단하는 규칙이라 LLM이 필요 없다 — assignee_recommend/rule_filter.py와
같은 원칙("코드가 결정, LLM은 서술만")을 여기서도 그대로 따른다.

원래는 이 필터링을 백엔드가 SQL WHERE절로 미리 걸러서 넘겨주는 방식으로
설계했었는데(2026-09-02 이전), 필터 기준이 바뀔 때마다 백엔드 SQL도 같이
맞춰줘야 해서 문서와 실제 구현이 어긋나기 쉬웠다. 그래서 백엔드는 필터링 없이
원본 사원 데이터를 그대로 넘기고, 이 에이전트가 rule_filter.py로 직접
걸러내는 쪽으로 바꿨다(2026-09-02 결정) — 필터 기준이 바뀌어도 이 파일만
고치면 된다.

가용시간(부하) 필터는 여기 없다 — 프로젝트를 한 번에 하나만 진행한다는
전제라 담당자매핑 시점엔 다들 이 프로젝트 기준 부하가 없고, 실제 상한 초과
여부는 assignee_recommend(A2-3)의 schedule_assignments()가 이미 걸러준다.
"""

import logging
from typing import Any, Dict, List, Optional

from .schemas import RawEmployeeProfile

logger = logging.getLogger(__name__)


def filter_candidates(
    raw_profiles: List[RawEmployeeProfile],
    tasks: List[Dict[str, Any]],
    needed_roles: Optional[List[str]] = None,
) -> List[RawEmployeeProfile]:
    """
    LLM 호출 전 후보를 거른다: 재직 중이고, 업무에 필요한 스킬을 하나라도 가진 사람.

    Args:
        raw_profiles: 필터링 전 사원 원본 목록
        tasks: 업무 생성(A2-2) 출력 — required_skills 합집합을 만드는 데 씀
        needed_roles: 더 이상 쓰지 않는다. 호출부 호환을 위해 시그니처만 남겨둠.

    2026-09-11: 직무(needed_roles) 게이트를 제거했다. 직무는 스킬의 거친 대리
    지표일 뿐이고 — assignee_recommend의 _fit_score도 직무를 안 본다 —, team_sizing의
    skill->role 매핑이 조금만 비어도 후보가 전원 탈락해 배분이 죽는 사고가 있었다
    (spec 108). 자격 판정은 "스킬을 실제로 갖고 있는가" 하나로 충분하다.
    """
    required_skills = {s for t in tasks for s in t.get("required_skills", [])}
    filtered = [
        p
        for p in raw_profiles
        if p.is_active and (not required_skills or (required_skills & set(p.skills)))
    ]
    if not filtered:
        logger.warning(
            "후보 0명 — 업무 required_skills(%s)를 가진 재직 사원이 없음",
            sorted(required_skills)[:10],
        )
    return filtered

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

from typing import Any, Dict, List

from .schemas import RawEmployeeProfile


def filter_candidates(
    raw_profiles: List[RawEmployeeProfile],
    tasks: List[Dict[str, Any]],
    needed_roles: List[str],
) -> List[RawEmployeeProfile]:
    """
    LLM 호출 전, 후보를 3단계로 거른다. 순서대로 하나라도 안 맞으면 제외한다.

    Args:
        raw_profiles: 필터링 전 사원 원본 목록 (재직 여부와 무관하게 전부 포함될 수 있음)
        tasks: 업무 생성(A2-2) 출력 그대로 — required_skills 합집합을 만드는 데 씀
        needed_roles: 팀 규모 추정(team_sizing) 출력의 by_role[].role 목록 —
            이 프로젝트에 필요하다고 판단된 직무 코드들

    Returns:
        세 조건을 모두 통과한 후보만 남긴 목록. 하나도 안 남으면 빈 리스트를
        반환한다(에이전트 쪽에서 별도 에러 처리 안 함 — 그냥 아무도 LLM을
        안 타는 것뿐이다).
    """
    required_skills = {s for t in tasks for s in t.get("required_skills", [])}
    needed_role_set = set(needed_roles)

    filtered = []
    for p in raw_profiles:
        if not p.is_active:
            continue
        if needed_role_set and p.job_role not in needed_role_set:
            continue
        if required_skills and not (required_skills & set(p.skills)):
            continue
        filtered.append(p)
    return filtered

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

2026-09-14: 가용시간(부하) 자체는 여전히 이 필터의 통과/탈락 기준이 아니다 —
스킬만 겹치면 일단 자격은 있다고 본다. 다만 "역할별 후보 상한"(아래
MAX_CANDIDATES_PER_ROLE)을 적용할 때, 상한으로 뽑은 소수가 그 역할 업무량을
감당하기엔 남는 가용시간이 부족하면 후보를 더 끌어오는 데에는 가용시간을 쓴다
(_select_capacity_aware 참고). 실제 상한 초과 여부의 최종 판정은 여전히
assignee_recommend(A2-3)의 schedule_assignments()가 한다 — 여기서 하는 건
"LLM에게 몇 명을 보여줄지"를 정하는 것뿐, "누구를 배정할지"는 그대로 A2-3 몫이다.

역할별 상한을 두는 이유(2026-09-14, 성능) — 이 필터를 통과한 인원 전체가
이후 두 군데 LLM 호출의 크기를 그대로 늘린다: (1) 이 모듈(assignee_mapping)의
경력기술서 태그 추출 배치 호출 수, (2) assignment_ranking.score_candidate_fit()이
업무 unit마다 프롬프트에 넣는 후보 목록(입력+출력 토큰이 후보 수에 비례). 스킬만
보는 느슨한 필터라 겹치는 사람이 많은 프로젝트에서는 이 두 호출이 LLM 응답시간의
실제 병목이 된다. 그래서 역할(스킬의 대리 지표 — team_sizing.SKILL_ROLE_MAP 참고)
별로 상위 MAX_CANDIDATES_PER_ROLE명만 남기되, 그 역할 업무량 대비 남는 가용시간이
부족하면 다음 순위 후보를 계속 추가해 배정 자체가 막히지 않게 한다. 호출부가
current_workload/total_workdays/skill_role_map을 안 넘기면(예: 아직 안 고친
호출부, 구 테스트) 이 상한을 건너뛰고 예전처럼 스킬 겹침만으로 전원 통과시킨다 —
성능 최적화일 뿐 자격 판정 자체를 바꾸는 게 아니므로 안전하게 꺼둘 수 있어야 한다.
"""

import logging
from typing import Any, Dict, List, Optional

from assignee_recommend.rule_filter import DEFAULT_RISK_BUFFER, plan_days
from team_sizing import role_hours

from .schemas import RawEmployeeProfile

logger = logging.getLogger(__name__)

# 역할별로 LLM에 보여줄 후보 상한. 이 역할의 후보가 이보다 적으면(대부분의 경우)
# 그냥 있는 만큼만 쓴다 — 억지로 채우지 않는다.
MAX_CANDIDATES_PER_ROLE = 5


def _role_skill_sets(skill_role_map: Dict[str, Dict[str, float]]) -> Dict[str, set]:
    """skill -> {role: weight} 매핑을 role -> {skill, ...} 로 뒤집는다."""
    out: Dict[str, set] = {}
    for skill, dist in skill_role_map.items():
        for role in dist:
            out.setdefault(role, set()).add(skill)
    return out


def _role_match_quality(profile: RawEmployeeProfile, role_skills: set) -> float:
    """이 후보가 그 역할 스킬을 얼마나 잘 갖췄는지 — 매칭된 스킬의 평균 숙련도(1~5).
    숙련도 정보가 없는 스킬은 3(중간)으로 본다(assignee_recommend._match_skills와 동일 관례)."""
    matched = role_skills & set(profile.skills)
    if not matched:
        return 0.0
    return sum(profile.skill_levels.get(s, 3) for s in matched) / len(matched)


def _remaining_capacity_days(
    profile: RawEmployeeProfile, current_workload: Dict[str, float], total_workdays: int
) -> int:
    """이 프로젝트 기간 안에서 이 사람이 아직 쓸 수 있는 평일 수. 이미 확정된
    다른 업무(current_workload, 시간)를 기본 리스크 버퍼로 평일 환산해 뺀다 —
    schedule_assignments()가 기존 부하를 추정하는 방식과 동일(rule_filter.py 참고)."""
    hours = current_workload.get(profile.employee_id, 0.0)
    committed_days = plan_days(hours, DEFAULT_RISK_BUFFER)
    return max(0, total_workdays - committed_days)


def _select_capacity_aware(
    base_filtered: List[RawEmployeeProfile],
    tasks: List[Dict[str, Any]],
    current_workload: Dict[str, float],
    total_workdays: int,
    skill_role_map: Dict[str, Dict[str, float]],
    max_per_role: int,
) -> List[RawEmployeeProfile]:
    """역할별로 상위 max_per_role명만 남기되, 선택된 인원의 남은 가용일수 합이
    그 역할의 예상 소요일수(role_hours 기반)에 못 미치면 다음 순위 후보를 계속
    추가한다. 매핑이 없는 스킬(UNMAPPED_ROLE — 팀에 그 역량을 가진 사람이 없다는
    신호)은 역할로 묶을 수 없어 상한 없이 그대로 통과시킨다.

    2026-09-14 수정 — 역할 간 가용일수 중복 계산 버그: 한 사람이 여러 역할에
    걸치면(예: Django+MySQL 보유자는 BACKEND/DATA_ENGINEER 둘 다에 후보로 잡힘)
    그 사람의 "남는 평일 수"를 역할마다 독립적으로 세면 실제로는 하루를 두 역할에
    동시에 못 쓰는데도 커버리지가 이중으로 잡혀, 확장이 필요한데도 "이미
    충분하다"고 일찍 멈출 수 있었다. 그래서 모든 역할이 공유하는 가용일수
    풀(remaining_pool)을 하나 두고, 한 역할의 커버리지 계산에 쓰인 사람은 그
    풀에서 소진 처리한다(다음 역할 계산엔 0으로 잡힘) — 실제 배정 가능 여부는
    여전히 schedule_assignments가 최종 판단하므로, 여기서는 과소추정(중복 계산으로
    확장을 덜 하는 것)보다 과대추정(후보를 조금 더 넉넉히 남기는 것) 쪽으로
    치우치는 게 안전하다.
    """
    role_skills = _role_skill_sets(skill_role_map)
    hours_by_role = role_hours(tasks, skill_role_map)
    required_skills = {s for t in tasks for s in t.get("required_skills", [])}
    roles_needed = {role for skill in required_skills for role in (skill_role_map.get(skill) or {})}
    unmapped_skills = {s for s in required_skills if not skill_role_map.get(s)}

    keep_ids: set = set()
    for p in base_filtered:
        if set(p.skills) & unmapped_skills:
            keep_ids.add(p.employee_id)

    remaining_pool: Dict[str, int] = {
        p.employee_id: _remaining_capacity_days(p, current_workload, total_workdays) for p in base_filtered
    }

    # 2026-09-15: 두 번째 정렬 키(role 이름)로 동점 시 순서를 고정한다 — roles_needed가
    # set이라 str 원소의 반복 순서는 프로세스마다 해시가 랜덤이라, 시간이 같은 두 역할이
    # 있으면 동점 정렬(sorted는 stable이지만 입력 순서 자체가 안정적이지 않음) 결과가
    # 프로세스마다 달라져 같은 입력에도 remaining_pool 소진 순서(→ 최종 후보)가 흔들릴
    # 수 있었다.
    for role in sorted(roles_needed, key=lambda r: (-hours_by_role.get(r, 0.0), r)):
        skills_for_role = role_skills.get(role, set())
        candidates = [p for p in base_filtered if set(p.skills) & skills_for_role]
        if not candidates:
            continue
        candidates.sort(
            key=lambda p: (
                -_role_match_quality(p, skills_for_role),
                -remaining_pool.get(p.employee_id, 0),
                p.employee_id,
            )
        )
        selected = candidates[:max_per_role]
        needed_days = plan_days(hours_by_role.get(role, 0.0), DEFAULT_RISK_BUFFER)
        covered_days = sum(remaining_pool.get(p.employee_id, 0) for p in selected)
        idx = max_per_role
        while covered_days < needed_days and idx < len(candidates):
            selected.append(candidates[idx])
            covered_days += remaining_pool.get(candidates[idx].employee_id, 0)
            idx += 1
        if len(selected) > max_per_role:
            logger.info(
                "역할 %s: 가용시간 부족으로 후보를 %d명 -> %d명으로 확장 (필요 %d평일, 상위 %d명 보유 %d평일)",
                role, max_per_role, len(selected), needed_days, max_per_role,
                sum(remaining_pool.get(p.employee_id, 0) for p in candidates[:max_per_role]),
            )
        keep_ids.update(p.employee_id for p in selected)
        # 이 역할의 커버리지로 이미 쓰인 사람은 풀에서 소진 처리 — 다음 역할
        # 계산에서 같은 남는 일수를 또 카운트하지 않는다.
        for p in selected:
            remaining_pool[p.employee_id] = 0

    return [p for p in base_filtered if p.employee_id in keep_ids]


def filter_candidates(
    raw_profiles: List[RawEmployeeProfile],
    tasks: List[Dict[str, Any]],
    needed_roles: Optional[List[str]] = None,
    *,
    current_workload: Optional[Dict[str, float]] = None,
    total_workdays: Optional[int] = None,
    skill_role_map: Optional[Dict[str, Dict[str, float]]] = None,
    max_candidates_per_role: int = MAX_CANDIDATES_PER_ROLE,
) -> List[RawEmployeeProfile]:
    """
    LLM 호출 전 후보를 거른다: 재직 중이고, 업무에 필요한 스킬을 하나라도 가진 사람.
    (역할별 상한까지 적용하면) 그중에서도 역할별 상위 후보로 다시 좁힌다.

    Args:
        raw_profiles: 필터링 전 사원 원본 목록
        tasks: 업무 생성(A2-2) 출력 — required_skills 합집합을 만드는 데 씀
        needed_roles: 더 이상 쓰지 않는다. 호출부 호환을 위해 시그니처만 남겨둠.
        current_workload / total_workdays / skill_role_map: 2026-09-14 신설,
            전부 있어야 역할별 상한을 적용한다(하나라도 없으면 이 단계를 건너뛰고
            예전처럼 스킬 겹침만으로 거른다). 호출부(services.py)가 채운다.
        max_candidates_per_role: 역할별로 LLM에 보여줄 상한.

    2026-09-11: 직무(needed_roles) 게이트를 제거했다. 직무는 스킬의 거친 대리
    지표일 뿐이고 — assignee_recommend의 _fit_score도 직무를 안 본다 —, team_sizing의
    skill->role 매핑이 조금만 비어도 후보가 전원 탈락해 배분이 죽는 사고가 있었다
    (spec 108). 자격 판정은 "스킬을 실제로 갖고 있는가" 하나로 충분하다.

    2026-09-18 :PM은 무조건 제외하는 규칙 추가
    """
    required_skills = {s for t in tasks for s in t.get("required_skills", [])}
    filtered = [
        p
        for p in raw_profiles
        if p.is_active
        and p.job_role != "PROJECT_MANAGER"
        and (not required_skills or (required_skills & set(p.skills)))
    ]
    if not filtered:
        logger.warning(
            "후보 0명 — 업무 required_skills(%s)를 가진 재직 사원이 없음",
            sorted(required_skills)[:10],
        )
        return filtered

    if skill_role_map is not None and total_workdays is not None and current_workload is not None:
        before = len(filtered)
        filtered = _select_capacity_aware(
            filtered, tasks, current_workload or {}, total_workdays, skill_role_map, max_candidates_per_role,
        )
        if len(filtered) < before:
            logger.info(
                "역할별 후보 상한(%d명) 적용 — LLM 호출 대상 %d명 -> %d명",
                max_candidates_per_role, before, len(filtered),
            )
    return filtered

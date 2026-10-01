"""
ai/work_package.py

2026-09-11 (Phase 2 item 7): 배정 단위(unit)를 WorkPackage로 묶는 순수 계산 모듈.
2026-09-11 (Phase 3 item 10-11): LLM 분할 판단(assignment_ranking) 결과를 받아
패키지를 하위 패키지로 쪼개는 apply_split_decisions() 추가.

"어느 업무가 한 기능인지"의 1차 판단은 task_generation이 각 Task의 feature_area로
내렸고(A2-2), 이 모듈은 그 라벨대로 코드가 묶는다. "이 묶음을 한 사람에게 다 맡길지"
는 assignment_ranking(LLM)이 split 여부만 판단하고, 실제로 어느 unit끼리 나눌지는
여기(코드)가 확정한다 — "코드가 결정, LLM은 판단 입력만".

WorkPackage = "한 덩어리로 한 담당자에게 연속 배정하면 좋은 unit 묶음".
그룹 키:
  - feature_area가 있으면 그 값 (요구사항/Epic을 가로질러 묶일 수 있다)
  - 없으면 source_req_id로 대체 (= 기존 assignee_recommend의 요구사항 단위 응집도)
"""

import logging
from typing import Any, Dict, List, Optional

from team_sizing import SKILL_ROLE_MAP, UNMAPPED_ROLE

logger = logging.getLogger(__name__)


def _group_key(unit: Dict[str, Any]) -> str:
    feature = (unit.get("feature_area") or "").strip()
    if feature:
        return f"feature:{feature}"
    return f"req:{unit['source_req_id']}"


def assemble_packages(
    units: List[Dict[str, Any]], package_by_unit: Dict[str, str]
) -> List[Dict[str, Any]]:
    """package_by_unit 매핑대로 unit을 모아 package dict 목록을 만든다.
    package 등장 순서(unit 순회 기준)를 보존한다. 분할(apply_split_decisions) 후의
    매핑으로도 그대로 호출할 수 있다 — 그때는 WP-002-a 같은 하위 id가 나온다."""
    order: List[str] = []
    members: Dict[str, List[Dict[str, Any]]] = {}
    for u in units:
        pid = package_by_unit.get(u["unit_id"])
        if pid is None:
            continue
        if pid not in members:
            members[pid] = []
            order.append(pid)
        members[pid].append(u)

    packages: List[Dict[str, Any]] = []
    for pid in order:
        group = members[pid]
        skills: List[str] = []
        req_ids: List[str] = []
        for u in group:
            for s in u.get("required_skills") or []:
                if s not in skills:
                    skills.append(s)
            if u["source_req_id"] not in req_ids:
                req_ids.append(u["source_req_id"])
        packages.append(
            {
                "package_id": pid,
                "feature_area": group[0].get("feature_area"),
                "unit_ids": [u["unit_id"] for u in group],
                "estimated_hours": round(sum(u["estimated_hours"] for u in group), 1),
                "required_skills": skills,
                "source_req_ids": req_ids,
                "dependency_package_ids": [],  # 아래에서 채움
            }
        )

    # unit 의존성 -> package 의존성 (표시·PM 검토용; 실제 일정은 스케줄러가 unit
    # 단위 depends_on으로 계산한다).
    for pkg in packages:
        own = set(pkg["unit_ids"])
        dep_pids: List[str] = []
        for u in units:
            if u["unit_id"] not in own:
                continue
            for dep_uid in u.get("depends_on") or []:
                dep_pid = package_by_unit.get(dep_uid)
                if dep_pid and dep_pid != pkg["package_id"] and dep_pid not in dep_pids:
                    dep_pids.append(dep_pid)
        pkg["dependency_package_ids"] = dep_pids

    return packages


def build_work_packages(units: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Args:
        units: flatten_assignable_units() 결과

    Returns:
        {"packages": [...], "package_by_unit": {unit_id: package_id}}

    그룹 키가 unit마다 정확히 하나 나오므로 모든 unit이 정확히 하나의 package에
    들어간다 (assert_full_coverage로 재확인).
    """
    order: List[str] = []
    key_members: Dict[str, List[str]] = {}
    for u in units:
        key = _group_key(u)
        if key not in key_members:
            key_members[key] = []
            order.append(key)
        key_members[key].append(u["unit_id"])

    package_by_unit: Dict[str, str] = {}
    for idx, key in enumerate(order, start=1):
        pid = f"WP-{idx:03d}"
        for uid in key_members[key]:
            package_by_unit[uid] = pid

    return {"packages": assemble_packages(units, package_by_unit), "package_by_unit": package_by_unit}


def assert_full_coverage(package_by_unit: Dict[str, str], units: List[Dict[str, Any]]) -> None:
    """모든 배정 단위가 정확히 1개 package에 매핑됐는지 검증. 아니면 ValueError."""
    unit_ids = {u["unit_id"] for u in units}
    mapped = set(package_by_unit)
    missing = sorted(unit_ids - mapped)
    extra = sorted(mapped - unit_ids)
    if missing or extra:
        raise ValueError(
            f"WorkPackage 커버리지 불일치 — 누락 unit: {missing}, 존재하지 않는 unit: {extra}"
        )


# ---------------------------------------------------------------------------
# 2026-09-11 (Phase 3): LLM 분할 판단 적용
# ---------------------------------------------------------------------------
def _validate_groups(groups: List[List[str]], member_uids: List[str]) -> Optional[List[List[str]]]:
    """LLM이 준 unit_groups가 이 패키지 unit들의 정확한 분할(partition)인지 검증.
    맞으면 그대로, 아니면 None(코드 자동 분할로 폴백)."""
    if len(groups) < 2:
        return None
    flat = [uid for g in groups for uid in g]
    if len(flat) != len(set(flat)):
        return None  # 중복
    if set(flat) != set(member_uids):
        return None  # 누락 또는 외부 unit
    if any(len(g) == 0 for g in groups):
        return None
    return groups


def _dominant_role(unit: Dict[str, Any]) -> str:
    skills = unit.get("required_skills") or []
    for s in skills:
        role = SKILL_ROLE_MAP.get(s)
        if role:
            return role
    return UNMAPPED_ROLE


def _auto_groups(pkg_units: List[Dict[str, Any]]) -> Optional[List[List[str]]]:
    """코드 자동 분할: 요구사항이 2개 이상이면 요구사항별, 아니면 역할별.
    둘 다 1그룹이면 None(분할 불가)."""
    by_req: Dict[str, List[str]] = {}
    for u in pkg_units:
        by_req.setdefault(u["source_req_id"], []).append(u["unit_id"])
    if len(by_req) >= 2:
        return list(by_req.values())

    by_role: Dict[str, List[str]] = {}
    for u in pkg_units:
        by_role.setdefault(_dominant_role(u), []).append(u["unit_id"])
    if len(by_role) >= 2:
        return list(by_role.values())
    return None


def apply_split_decisions(
    units: List[Dict[str, Any]],
    package_by_unit: Dict[str, str],
    split_decisions: Dict[str, Dict[str, Any]],
) -> Dict[str, str]:
    """
    split_decisions: {package_id: {"reason": str, "unit_groups": [[unit_id, ...], ...]}}
      — assignment_ranking.agent.decide_package_splits() 출력. split=false인 패키지는
      애초에 여기 없다.

    split된 패키지의 unit들에 하위 package_id(WP-00X-a, WP-00X-b, ...)를 재부여한
    새 package_by_unit을 반환한다. unit_groups가 유효한 partition이면 그대로 쓰고,
    아니면 코드가 요구사항/역할 기준으로 자동 분할한다. 하위 그룹이 1개뿐이면
    분할을 취소한다.
    """
    units_by_id = {u["unit_id"]: u for u in units}
    pkg_members: Dict[str, List[str]] = {}
    for uid, pid in package_by_unit.items():
        pkg_members.setdefault(pid, []).append(uid)

    new_map = dict(package_by_unit)
    for pid, decision in split_decisions.items():
        member_uids = pkg_members.get(pid, [])
        if len(member_uids) < 2:
            continue

        groups = _validate_groups(decision.get("unit_groups") or [], member_uids)
        if groups is None:
            groups = _auto_groups([units_by_id[u] for u in member_uids if u in units_by_id])
        if not groups or len(groups) < 2:
            logger.info("패키지 %s: 분할 판단됐으나 하위 그룹을 못 만들어 분할 취소", pid)
            continue

        for gi, group in enumerate(groups):
            sub_pid = f"{pid}-{chr(ord('a') + gi)}"
            for uid in group:
                new_map[uid] = sub_pid
        logger.info("패키지 %s -> %d개로 분할 (%s)", pid, len(groups), decision.get("reason", ""))

    return new_map

"""
assignment_ranking/agent.py

2026-09-11 (Phase 3 item 10-11): WorkPackage 분할 판단 + 후보 질적 적합도 판단.

두 판단 모두 같은 "절충" 방식이다 — LLM은 판단 입력 하나만 주고, 실행(어느
unit끼리 나눌지 / 누구에게 최종 배정할지 / 용량 추적)은 전부 코드가 한다.

  - decide_package_splits: "이 기능 묶음을 한 사람에게 다 맡길지, 나눌지"만
    판단(split 여부 + 이유). 실제 분할은 work_package.apply_split_decisions().
  - score_candidate_fit: 코드가 스킬로 이미 좁힌 소수 후보의 경력기술서·자격증·
    숙련도 "내용"을 업무 설명과 대조해 질적 적합도(0~1)만 판단. 최종 선택·용량
    추적은 assignee_recommend.rule_filter.schedule_assignments()가 한다.

비용/지연 관리(두 함수 공통 패턴):
  - 코드 사전 필터로 "물어볼 필요 없는" 대상은 아예 LLM에 안 보낸다.
  - 남은 대상만 배치로 묶어 호출한다.
  - LLM 호출이 실패하면 해당 대상은 결과에서 빠지고, 호출부가 결정적 폴백으로
    처리한다(파이프라인을 막지 않는다).
"""

import logging
from typing import Any, Dict, List

from pydantic import ValidationError

from shared.llm_client import create_structured
from shared.retry_config import DEFAULT_MAX_TOKENS, MAX_RETRIES, TEMPERATURE_STRUCTURED
from team_sizing import SKILL_ROLE_MAP, UNMAPPED_ROLE
from assignee_recommend.rule_filter import _match_skills

from .prompt_builder import build_candidate_fit_prompt, build_split_prompt
from .schemas import CandidateFitBatch, PackageSplitBatch

logger = logging.getLogger(__name__)


def _roles_in(pkg_units: List[Dict[str, Any]]) -> set:
    roles = set()
    for u in pkg_units:
        skills = u.get("required_skills") or []
        mapped = [SKILL_ROLE_MAP[s] for s in skills if s in SKILL_ROLE_MAP]
        roles.update(mapped or [UNMAPPED_ROLE])
    return {r for r in roles if r != UNMAPPED_ROLE}


def _package_needs_llm(pkg: Dict[str, Any], pkg_units: List[Dict[str, Any]], max_hours: float) -> bool:
    """명백히 1인분이면 False — LLM에 안 물어본다."""
    if len(pkg_units) <= 1:
        return False
    if len(_roles_in(pkg_units)) >= 2:
        return True
    if max_hours > 0 and pkg.get("estimated_hours", 0.0) > max_hours:
        return True
    if len(pkg.get("source_req_ids") or []) >= 2 and len(pkg_units) >= 3:
        return True
    return False


def decide_package_splits(
    packages: List[Dict[str, Any]],
    units_by_id: Dict[str, Dict[str, Any]],
    max_hours_per_assignee: float,
) -> Dict[str, Dict[str, Any]]:
    """
    Returns:
        {package_id: {"reason": str, "unit_groups": [[unit_id, ...], ...]}}
        — split=true로 판단된 패키지만. 그 외(사전 필터 통과 못 함 / LLM이 false /
          호출 실패)는 키가 없다. work_package.apply_split_decisions()가 소비한다.
    """
    payload: List[Dict[str, Any]] = []
    for pkg in packages:
        pkg_units = [units_by_id[uid] for uid in pkg["unit_ids"] if uid in units_by_id]
        if not _package_needs_llm(pkg, pkg_units, max_hours_per_assignee):
            continue
        payload.append(
            {
                "package_id": pkg["package_id"],
                "feature_area": pkg.get("feature_area"),
                "estimated_hours": pkg.get("estimated_hours"),
                "source_req_ids": pkg.get("source_req_ids"),
                "units": [
                    {
                        "unit_id": u["unit_id"],
                        "title": u.get("title"),
                        "required_skills": u.get("required_skills") or [],
                        "estimated_hours": u.get("estimated_hours"),
                    }
                    for u in pkg_units
                ],
            }
        )

    if not payload:
        return {}

    try:
        batch: PackageSplitBatch = create_structured(
            system_prompt=build_split_prompt(payload, max_hours_per_assignee),
            user_message="각 기능 묶음을 분할할지 판단하라.",
            response_model=PackageSplitBatch,
            max_tokens=DEFAULT_MAX_TOKENS,
            temperature=TEMPERATURE_STRUCTURED,
            max_retries=MAX_RETRIES,
        )
    except ValidationError as e:
        logger.warning("패키지 분할 판단 스키마 검증 실패 — 분할 없이 진행: %s", e)
        return {}
    except Exception as e:
        logger.warning("패키지 분할 판단 LLM 호출 실패 — 분할 없이 진행: %s", e)
        return {}

    asked = {p["package_id"] for p in payload}
    result: Dict[str, Dict[str, Any]] = {}
    for d in batch.decisions:
        if d.split and d.package_id in asked:
            result[d.package_id] = {"reason": d.reason, "unit_groups": d.unit_groups}
    return result


# ---------------------------------------------------------------------------
# 2026-09-11: 후보 질적 적합도
# ---------------------------------------------------------------------------
FIT_BATCH_SIZE = 6  # unit 단위 배치 크기 — unit마다 후보 여러 명이 딸려오므로 작게 둔다
MIN_CANDIDATES_FOR_FIT_LLM = 2  # 후보가 1명 이하면 순위를 매길 필요가 없다 — 안 물어봄


def _candidates_for_unit(unit: Dict[str, Any], members: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """이 unit의 required_skills와 하나라도 겹치는 후보만 — 용량(상한)은 여기서
    안 본다(schedule_assignments의 그리디 루프 진행에 따라 바뀌는 값이라 이 단계
    에선 정적인 스킬 풀만 본다)."""
    required = set(unit.get("required_skills") or [])
    if not required:
        return list(members)
    out = []
    for m in members:
        if _match_skills(required, set(m.get("skills") or []), m.get("skill_levels")):
            out.append(m)
    return out


def score_candidate_fit(
    units: List[Dict[str, Any]], members: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    업무별로 이미 스킬 기준으로 좁혀진 소수 후보의 경력기술서·자격증·숙련도
    "내용"을 업무 설명과 대조해 질적 적합도를 판단한다.

    Returns:
        {unit_id: {employee_id: {"score": float, "reason": str}}}
        후보가 1명뿐이거나 스킬 요구가 없어 판단이 무의미한 unit, 그리고 LLM
        호출이 실패한 배치의 unit들은 결과에 없다 — assignee_recommend.rule_filter
        의 _fit_score가 이 경우 기존 개수 기반 계산으로 폴백한다.

    최종 배정(누구에게)·용량 추적·부하 누적은 이 함수가 하지 않는다 — 전부
    schedule_assignments()(코드)의 몫이고, 여기서 나온 점수는 그 함수가 쓰는
    _fit_score의 입력 하나일 뿐이다.
    """
    unit_payload: List[Dict[str, Any]] = []
    for u in units:
        candidates = _candidates_for_unit(u, members)
        if len(candidates) < MIN_CANDIDATES_FOR_FIT_LLM:
            continue
        unit_payload.append(
            {
                "unit_id": u["unit_id"],
                "title": u.get("title"),
                "description": u.get("description"),
                "required_skills": u.get("required_skills") or [],
                "candidates": [
                    {
                        "employee_id": m["employee_id"],
                        "skills_with_level": m.get("skill_levels") or {},
                        "certifications": m.get("certifications") or [],
                        "career_history_tags": m.get("past_similar_tasks") or [],
                    }
                    for m in candidates
                ],
            }
        )

    if not unit_payload:
        return {}

    result: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for i in range(0, len(unit_payload), FIT_BATCH_SIZE):
        chunk = unit_payload[i : i + FIT_BATCH_SIZE]
        try:
            batch: CandidateFitBatch = create_structured(
                system_prompt=build_candidate_fit_prompt(chunk),
                user_message="각 업무에 대해 후보들의 적합도를 판단하라.",
                response_model=CandidateFitBatch,
                max_tokens=DEFAULT_MAX_TOKENS,
                temperature=TEMPERATURE_STRUCTURED,
                max_retries=MAX_RETRIES,
            )
        except ValidationError as e:
            logger.warning("후보 적합도 판단 스키마 검증 실패(배치) — 개수 기반으로 폴백: %s", e)
            continue
        except Exception as e:
            logger.warning("후보 적합도 판단 LLM 호출 실패(배치) — 개수 기반으로 폴백: %s", e)
            continue

        for unit_fit in batch.units:
            result[unit_fit.unit_id] = {
                c.employee_id: {"score": c.fit_score, "reason": c.reason} for c in unit_fit.candidates
            }
    return result

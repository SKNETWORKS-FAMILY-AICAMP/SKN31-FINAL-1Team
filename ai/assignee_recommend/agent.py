"""
a2_3_assignee_recommend/agent.py

AI 담당자 추천 (FR-05-016, 017)
그리디 스케줄러(코드)가 우선순위(요구사항 priority 상속) 순으로 업무를 정렬해
가용시간이 남은 최적 담당자에게 순차 배정을 "확정"한다. LLM은 그 결과에 대한
근거 문장(정상 배정) 또는 보류 사유 설명(후보 없음)만 생성한다 — 사람이 이
추천을 검토·승인하기 전까지는 확정 배정이 아니라 어디까지나 "추천"이다.

이 모듈은 DB를 모른다:
  - state["member_profiles"] — 같은 그래프 안에서 앞서 실행된 assignee_mapping_node의
    출력을 그대로 이어받는다 (별도 조회 불필요).
  - state["current_workload"] — task 테이블에서 assignee_id 기준 SUM(estimated_hours)한
    값. 호출부(Django/Celery task)가 A2-3 실행 직전에 최신값으로 채워야 한다 — 사람
    검토 게이트로 오래 멈춰 있었을 수 있어, 파이프라인 시작 시점 값을 그대로 쓰면 낡을
    수 있다 (ai/ ↔ backend 통합 방식 B안, 2026-08-30 결정).
  - state["project_start_date"] / state["project_end_date"] — project.start_date/
    end_date 값 그대로("YYYY-MM-DD"). 담당자 1인당 배정 상한(주 40시간 x 기간 주수)을
    계산하는 데 쓴다. DB 조회 없이 두 날짜만 있으면 되는 순수 계산이라 이 모듈
    안에서 직접 계산한다 (rule_filter.calculate_max_hours_per_assignee 참고).
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError

from shared.llm_client import create_structured
from shared.retry_config import DEFAULT_MAX_TOKENS, MAX_RETRIES, TEMPERATURE_STRUCTURED

from .prompt_builder import (
    build_batch_hold_prompt,
    build_batch_reason_prompt,
    build_hold_prompt,
    build_reason_prompt,
)
from .rule_filter import (
    calculate_max_hours_per_assignee,
    flatten_assignable_units,
    schedule_assignments,
    sort_units_by_priority,
)
from .schemas import (
    AssignmentResult,
    BatchHoldExplanations,
    BatchRecommendationReasons,
    HoldExplanation,
    RecommendationReason,
)

logger = logging.getLogger(__name__)

# 배치 하나에 몰아넣는 unit 수 상한 (FR-05-016/017 성능 개선, 2026-09).
# 이전엔 확정된 unit마다 LLM을 1회씩 호출해서 "업무 배분 실행" 한 번에
# 10~20건 이상의 순차 LLM 호출이 발생했고, 이게 OpenAI TPM(분당 토큰) 한도를
# 자주 넘겨 느려지거나 실패했다. unit들을 묶어 한 번에 보내면 호출 수 자체가
# 줄어 총 대기시간과 레이트리밋 위험이 크게 줄어든다. 다만 한 요청에 너무
# 많이 몰아넣으면 프롬프트가 커져 단일 요청 토큰 상한/순간 TPM을 다시 넘길
# 수 있으므로, 청크로 나눠 여러 번 호출한다 — 그래도 "unit당 1회"보다는
# 훨씬 적은 호출 수(ceil(N/CHUNK)번)가 된다.
BATCH_CHUNK_SIZE = 10


def _priority_by_req_id(requirement_doc: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """요구사항 ID -> priority. 업무는 자기 자신에 priority가 없고 요구사항에서 상속받는다."""
    return {r["id"]: r.get("priority") for r in requirement_doc.get("requirements", [])}


def _chunk(items: List[Any], size: int) -> List[List[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def generate_reason(unit: Dict[str, Any], candidate: Dict[str, Any]) -> RecommendationReason:
    """단건 근거 생성 — 배치 응답에서 특정 unit_id가 누락됐을 때의 폴백으로도 쓰인다."""
    prompt = build_reason_prompt(unit, candidate)
    return create_structured(
        system_prompt=prompt,
        user_message="위 후보에 대한 추천 근거를 작성하라.",
        response_model=RecommendationReason,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=TEMPERATURE_STRUCTURED,
        max_retries=MAX_RETRIES,
    )


def generate_hold_explanation(unit: Dict[str, Any]) -> HoldExplanation:
    """단건 보류 사유 생성 — 배치 응답에서 특정 unit_id가 누락됐을 때의 폴백으로도 쓰인다."""
    prompt = build_hold_prompt(unit)
    return create_structured(
        system_prompt=prompt,
        user_message="이 업무가 왜 배정 보류됐는지 설명하라.",
        response_model=HoldExplanation,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=TEMPERATURE_STRUCTURED,
        max_retries=MAX_RETRIES,
    )


def generate_batch_reasons(
    units_and_candidates: List[Tuple[Dict[str, Any], Dict[str, Any]]]
) -> Dict[str, RecommendationReason]:
    """
    (unit, 확정된 담당자) 목록에 대한 근거 문장을 unit_id 당 1회가 아니라
    청크(BATCH_CHUNK_SIZE)당 1회의 LLM 호출로 받는다.

    반환: {unit_id: RecommendationReason}. 배치 응답에 특정 unit_id가 빠져
    있으면(LLM이 그 항목을 놓친 경우) — 전체 배치를 실패시키지 않고 그
    unit 하나만 기존 단건 호출(generate_reason)로 보완한다. 배치 실패를
    이유로 이미 잘 받은 나머지 결과까지 버리는 것보다, 소수의 예외 케이스에
    대해서만 추가 호출 1회를 감수하는 편이 훨씬 저렴하고 안전하기 때문이다.
    """
    results: Dict[str, RecommendationReason] = {}
    for chunk in _chunk(units_and_candidates, BATCH_CHUNK_SIZE):
        prompt = build_batch_reason_prompt(chunk)
        batch = create_structured(
            system_prompt=prompt,
            user_message="위 업무 목록 전체에 대한 추천 근거를 각각 작성하라.",
            response_model=BatchRecommendationReasons,
            max_tokens=DEFAULT_MAX_TOKENS,
            temperature=TEMPERATURE_STRUCTURED,
            max_retries=MAX_RETRIES,
        )
        by_id = {item.unit_id: item.reason for item in batch.results}
        for unit, candidate in chunk:
            unit_id = unit["unit_id"]
            if unit_id in by_id:
                results[unit_id] = by_id[unit_id]
            else:
                logger.warning(
                    "unit_id=%s: 배치 근거 응답에 누락되어 단건 호출로 보완", unit_id
                )
                results[unit_id] = generate_reason(unit, candidate)
    return results


def generate_batch_hold_explanations(units: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    보류된 unit 목록에 대한 사유 설명을 unit_id 당 1회가 아니라 청크당 1회의
    LLM 호출로 받는다. 결측 unit_id 처리 정책은 generate_batch_reasons와 동일
    (단건 호출로 보완).
    """
    results: Dict[str, str] = {}
    for chunk in _chunk(units, BATCH_CHUNK_SIZE):
        prompt = build_batch_hold_prompt(chunk)
        batch = create_structured(
            system_prompt=prompt,
            user_message="위 업무 목록 전체에 대해 왜 배정이 보류됐는지 각각 설명하라.",
            response_model=BatchHoldExplanations,
            max_tokens=DEFAULT_MAX_TOKENS,
            temperature=TEMPERATURE_STRUCTURED,
            max_retries=MAX_RETRIES,
        )
        by_id = {item.unit_id: item.explanation for item in batch.results}
        for unit in chunk:
            unit_id = unit["unit_id"]
            if unit_id in by_id:
                results[unit_id] = by_id[unit_id]
            else:
                logger.warning(
                    "unit_id=%s: 배치 보류 사유 응답에 누락되어 단건 호출로 보완", unit_id
                )
                results[unit_id] = generate_hold_explanation(unit).explanation
    return results


def assignee_recommend_node(state: Dict[str, Any]) -> Dict[str, Any]:
    missing = [
        k
        for k in ("member_profiles", "current_workload", "project_start_date", "project_end_date")
        if k not in state
    ]
    if missing:
        return {"error": f"MISSING_INPUT: state{missing} — 호출부가 미리 채워야 함"}

    members = state["member_profiles"]
    current_workload = state["current_workload"]

    try:
        max_hours_per_assignee = calculate_max_hours_per_assignee(
            state["project_start_date"], state["project_end_date"]
        )
    except ValueError as e:
        return {"error": f"INVALID_INPUT: {e}"}

    requirement_doc = state.get("requirement_doc", {})
    priority_map = _priority_by_req_id(requirement_doc)

    # 1. 배정 대상 단위를 뽑아 우선순위 순으로 정렬한다 (Task별 독립 처리가 아니라
    #    프로젝트 전체를 한 번에 순회해야 부하 누적이 순서대로 반영된다).
    units = flatten_assignable_units(state.get("tasks", []))
    units = sort_units_by_priority(units, priority_map)

    # 2. 코드가 전체 배정을 한 번에 확정한다 (LLM 개입 없음).
    scheduled = schedule_assignments(units, members, current_workload, max_hours_per_assignee)

    # 3. 확정된 결과를 "배정됨"/"보류"로 나눠, 그룹별로 최대 1회(또는 청크 단위로
    #    ceil(N/BATCH_CHUNK_SIZE)회)의 배치 LLM 호출로 근거 문장/보류 사유를 채운다.
    #    예전엔 unit마다 별도 호출이었지만(N개면 N번), 이제 최대 2번(각 그룹당 1번,
    #    그룹이 크면 청크당 1번씩)으로 줄어든다.
    assigned_items = [item for item in scheduled if item["employee_id"] is not None]
    held_items = [item for item in scheduled if item["employee_id"] is None]

    try:
        reason_by_unit_id: Dict[str, RecommendationReason] = {}
        if assigned_items:
            reason_by_unit_id = generate_batch_reasons(
                [(item["unit"], item) for item in assigned_items]
            )

        hold_by_unit_id: Dict[str, str] = {}
        if held_items:
            hold_by_unit_id = generate_batch_hold_explanations(
                [item["unit"] for item in held_items]
            )
    except ValidationError as e:
        logger.error("A2-3 스키마 검증 실패: %s", e)
        return {"error": f"SCHEMA_VALIDATION_FAILED: {e}"}
    except Exception as e:
        logger.exception("A2-3 실행 중 오류")
        return {"error": f"GENERATION_FAILED: {e}"}

    # 4. 배치 결과를 unit_id로 다시 매핑해 기존과 동일한 형태의 assignments를 만든다
    #    (여기서부터는 순서·필드 구성 모두 배치 도입 이전과 동일하게 유지한다).
    assignments = []
    try:
        for item in scheduled:
            unit = item["unit"]
            unit_id = unit["unit_id"]
            if item["employee_id"] is None:
                result = AssignmentResult(
                    unit_id=unit_id,
                    parent_task_id=unit["parent_task_id"],
                    source_req_id=unit["source_req_id"],
                    review_required=True,
                    hold_explanation=hold_by_unit_id[unit_id],
                )
                logger.warning("unit_id=%s: 조건을 만족하는 후보가 없어 보류 처리", unit_id)
            else:
                result = AssignmentResult(
                    unit_id=unit_id,
                    parent_task_id=unit["parent_task_id"],
                    source_req_id=unit["source_req_id"],
                    employee_id=item["employee_id"],
                    score=item["score"],
                    reason=reason_by_unit_id[unit_id],
                    review_required=False,
                )
            assignments.append(result.model_dump(mode="json"))
    except ValidationError as e:
        logger.error("A2-3 스키마 검증 실패: %s", e)
        return {"error": f"SCHEMA_VALIDATION_FAILED: {e}"}
    except Exception as e:
        logger.exception("A2-3 실행 중 오류")
        return {"error": f"GENERATION_FAILED: {e}"}

    return {"assignments": assignments, "error": None}

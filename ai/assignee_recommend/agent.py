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
from typing import Any, Dict, Optional

from pydantic import ValidationError

from shared.llm_client import create_structured
from shared.retry_config import DEFAULT_MAX_TOKENS, MAX_RETRIES, TEMPERATURE_STRUCTURED

from .prompt_builder import build_hold_prompt, build_reason_prompt
from .rule_filter import (
    calculate_max_hours_per_assignee,
    flatten_assignable_units,
    schedule_assignments,
    sort_units_by_priority,
)
from .schemas import AssignmentResult, HoldExplanation, RecommendationReason

logger = logging.getLogger(__name__)


def _priority_by_req_id(requirement_doc: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """요구사항 ID -> priority. 업무는 자기 자신에 priority가 없고 요구사항에서 상속받는다."""
    return {r["id"]: r.get("priority") for r in requirement_doc.get("requirements", [])}


def generate_reason(unit: Dict[str, Any], candidate: Dict[str, Any]) -> RecommendationReason:
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
    prompt = build_hold_prompt(unit)
    return create_structured(
        system_prompt=prompt,
        user_message="이 업무가 왜 배정 보류됐는지 설명하라.",
        response_model=HoldExplanation,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=TEMPERATURE_STRUCTURED,
        max_retries=MAX_RETRIES,
    )


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

    # 3. 확정된 결과마다 LLM이 근거 문장 또는 보류 사유만 채운다.
    assignments = []
    for item in scheduled:
        unit = item["unit"]
        try:
            if item["employee_id"] is None:
                hold = generate_hold_explanation(unit)
                result = AssignmentResult(
                    unit_id=unit["unit_id"],
                    parent_task_id=unit["parent_task_id"],
                    source_req_id=unit["source_req_id"],
                    review_required=True,
                    hold_explanation=hold.explanation,
                )
                logger.warning("unit_id=%s: 조건을 만족하는 후보가 없어 보류 처리", unit["unit_id"])
            else:
                reason = generate_reason(unit, item)
                result = AssignmentResult(
                    unit_id=unit["unit_id"],
                    parent_task_id=unit["parent_task_id"],
                    source_req_id=unit["source_req_id"],
                    employee_id=item["employee_id"],
                    score=item["score"],
                    reason=reason,
                    review_required=False,
                )
        except ValidationError as e:
            logger.error("A2-3 스키마 검증 실패: %s", e)
            return {"error": f"SCHEMA_VALIDATION_FAILED: {e}"}
        except Exception as e:
            logger.exception("A2-3 실행 중 오류")
            return {"error": f"GENERATION_FAILED: {e}"}

        assignments.append(result.model_dump(mode="json"))

    return {"assignments": assignments, "error": None}

"""
a1_2_plan_draft/agent.py

기획서 초안 생성 (FR-03-004, 005)
반려 시 이 노드로 되돌아오며, state["plan_rejection_reason"]에 사유가 담겨 있다.
"""

import logging
from typing import Any, Dict

from pydantic import ValidationError

from shared.llm_client import get_client
from shared.retry_config import DEFAULT_MAX_TOKENS, DEFAULT_MODEL, MAX_RETRIES, TEMPERATURE_STRUCTURED

from .prompt_builder import build_system_prompt
from .schemas import PlanDocument

logger = logging.getLogger(__name__)


def generate_plan(structured_analysis: dict, rejection_reason: str | None = None) -> PlanDocument:
    client = get_client()
    system_prompt = build_system_prompt(structured_analysis, rejection_reason)

    return client.chat.completions.create(
        model=DEFAULT_MODEL,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=TEMPERATURE_STRUCTURED,
        system=system_prompt,
        messages=[{"role": "user", "content": "위 분석 결과를 바탕으로 기획서 초안을 생성하라."}],
        response_model=PlanDocument,
        max_retries=MAX_RETRIES,
    )


def plan_draft_node(state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        result = generate_plan(
            state["structured_analysis"], state.get("plan_rejection_reason")
        )
    except ValidationError as e:
        logger.error("A1-2 스키마 검증 실패: %s", e)
        return {"error": f"SCHEMA_VALIDATION_FAILED: {e}"}
    except Exception as e:
        logger.exception("A1-2 실행 중 오류")
        return {"error": f"GENERATION_FAILED: {e}"}

    return {"plan": result.model_dump(mode="json"), "error": None}

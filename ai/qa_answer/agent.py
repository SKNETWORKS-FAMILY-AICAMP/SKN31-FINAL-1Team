"""
b2_qa_answer/agent.py

RAG 기반 질의응답 + 근거출처 표시 (FR-04-001, 005)
"""

import logging
from typing import Any, Dict

from pydantic import ValidationError

from shared.llm_client import get_client
from shared.retry_config import DEFAULT_MAX_TOKENS, DEFAULT_MODEL, MAX_RETRIES, TEMPERATURE_GENERATIVE

from .prompt_builder import build_system_prompt
from .schemas import Answer

logger = logging.getLogger(__name__)


def answer_query(query: str, chunks: list[dict]) -> Answer:
    client = get_client()
    system_prompt = build_system_prompt(query, chunks)

    return client.chat.completions.create(
        model=DEFAULT_MODEL,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=TEMPERATURE_GENERATIVE,
        system=system_prompt,
        messages=[{"role": "user", "content": "위 청크를 근거로 질문에 답하라."}],
        response_model=Answer,
        max_retries=MAX_RETRIES,
    )


def qa_answer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Track B 전용 노드. Track A(graph.py)와는 별개의 흐름으로 호출된다
    (사용자가 챗봇에 질문을 입력할 때마다 B1 -> B2 순으로 실행).
    """
    try:
        result = answer_query(state["query"], state["chunks"])
    except ValidationError as e:
        logger.error("B2 스키마 검증 실패: %s", e)
        return {"error": f"SCHEMA_VALIDATION_FAILED: {e}"}
    except Exception as e:
        logger.exception("B2 실행 중 오류")
        return {"error": f"GENERATION_FAILED: {e}"}

    return {"answer": result.model_dump(mode="json"), "error": None}

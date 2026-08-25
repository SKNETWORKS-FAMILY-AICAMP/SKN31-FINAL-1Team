"""
a1_1_meeting_analysis/agent.py

회의록 AI 구조화 분석 (FR-03-003)
"""

import logging
from typing import Any, Dict

from pydantic import ValidationError

from shared.llm_client import get_client
from shared.retry_config import DEFAULT_MAX_TOKENS, DEFAULT_MODEL, MAX_RETRIES, TEMPERATURE_STRUCTURED

from .prompt_builder import build_system_prompt
from .schemas import MeetingAnalysis

logger = logging.getLogger(__name__)


def analyze_meeting(meeting_text: str) -> MeetingAnalysis:
    client = get_client()
    system_prompt = build_system_prompt(meeting_text)

    return client.chat.completions.create(
        model=DEFAULT_MODEL,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=TEMPERATURE_STRUCTURED,
        system=system_prompt,
        messages=[{"role": "user", "content": "위 회의록을 분석해 구조화하라."}],
        response_model=MeetingAnalysis,
        max_retries=MAX_RETRIES,
    )


def meeting_analysis_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph 노드 진입점. state['meeting_id']로 회의록을 조회해 분석한다."""
    # TODO(담당자1): meeting_id로 meeting_log 테이블(또는 S3) 조회 로직 연결
    meeting_text = state.get("meeting_text", "")  # 임시 — 실제로는 DB 조회 결과

    try:
        result = analyze_meeting(meeting_text)
    except ValidationError as e:
        logger.error("A1-1 스키마 검증 실패: %s", e)
        return {"error": f"SCHEMA_VALIDATION_FAILED: {e}"}
    except Exception as e:
        logger.exception("A1-1 실행 중 오류")
        return {"error": f"GENERATION_FAILED: {e}"}

    return {"structured_analysis": result.model_dump(mode="json"), "error": None}

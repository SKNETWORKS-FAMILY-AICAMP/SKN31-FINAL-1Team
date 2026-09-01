"""
a2_2_task_generation/agent.py

업무 자동 생성 (FR-05-014, 015)

FR-05-014 원문: "3개 이상 7개 이하이며, 참여인원 수 이상이어야 한다."
참여인원 수는 요구사항정의서 JSON 안에 없어 별도 조회가 필요하지만, 이 모듈은
DB를 모른다 — 호출부(Django/Celery task)가 미리 조회해 state["participant_count"]로
채워 넣는다는 전제다 (ai/ ↔ backend 통합 방식 B안, 2026-08-30 결정).
"""

import logging
from typing import Any, Dict

from pydantic import ValidationError

from shared.llm_client import create_structured
from shared.retry_config import DEFAULT_MAX_TOKENS, MAX_RETRIES, TEMPERATURE_STRUCTURED

from .prompt_builder import build_system_prompt
from .schemas import TaskList

logger = logging.getLogger(__name__)


def generate_tasks(requirement_doc: dict, participant_count: int) -> TaskList:
    system_prompt = build_system_prompt(requirement_doc, participant_count)

    return create_structured(
        system_prompt=system_prompt,
        user_message="위 요구사항정의서를 바탕으로 업무를 생성하라.",
        response_model=TaskList,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=TEMPERATURE_STRUCTURED,
        max_retries=MAX_RETRIES,
    )


def task_generation_node(state: Dict[str, Any]) -> Dict[str, Any]:
    if "participant_count" not in state:
        return {"error": "MISSING_INPUT: state['participant_count'] — 호출부가 미리 채워야 함"}
    participant_count = state["participant_count"]

    try:
        result = generate_tasks(state["requirement_doc"], participant_count)
    except ValidationError as e:
        logger.error("A2-2 스키마 검증 실패: %s", e)
        return {"error": f"SCHEMA_VALIDATION_FAILED: {e}"}
    except Exception as e:
        logger.exception("A2-2 실행 중 오류")
        return {"error": f"GENERATION_FAILED: {e}"}

    # 참여인원 수 이상인지 코드로 재검증 (스키마는 3~7 범위만 보장하므로)
    if len(result.tasks) < participant_count:
        logger.warning(
            "생성된 업무 수(%d)가 참여인원 수(%d)보다 적습니다", len(result.tasks), participant_count
        )

    return {"tasks": [t.model_dump(mode="json") for t in result.tasks], "error": None}

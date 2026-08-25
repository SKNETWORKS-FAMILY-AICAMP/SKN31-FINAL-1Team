"""
a2_2_task_generation/agent.py

업무 자동 생성 (FR-05-014, 015)

FR-05-014 원문: "3개 이상 7개 이하이며, 참여인원 수 이상이어야 한다."
참여인원 수는 요구사항정의서 JSON 안에 없으므로, 이 노드에서 별도로
member 테이블을 조회해 프롬프트 제약("min_tasks")에 반영한다.
"""

import logging
from typing import Any, Dict

from pydantic import ValidationError

from shared.llm_client import get_client
from shared.retry_config import DEFAULT_MAX_TOKENS, DEFAULT_MODEL, MAX_RETRIES, TEMPERATURE_STRUCTURED

from .prompt_builder import build_system_prompt
from .schemas import TaskList

logger = logging.getLogger(__name__)


def get_participant_count(project_id: str) -> int:
    """TODO(담당자2): member 테이블에서 project_id 기준 참여인원 수 조회."""
    # SELECT COUNT(*) FROM member WHERE project_id = %s
    raise NotImplementedError


def generate_tasks(requirement_doc: dict, participant_count: int) -> TaskList:
    client = get_client()
    system_prompt = build_system_prompt(requirement_doc, participant_count)

    return client.chat.completions.create(
        model=DEFAULT_MODEL,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=TEMPERATURE_STRUCTURED,
        system=system_prompt,
        messages=[{"role": "user", "content": "위 요구사항정의서를 바탕으로 업무를 생성하라."}],
        response_model=TaskList,
        max_retries=MAX_RETRIES,
    )


def task_generation_node(state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        participant_count = get_participant_count(state["project_id"])
    except NotImplementedError:
        return {"error": "NOT_IMPLEMENTED: get_participant_count"}

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

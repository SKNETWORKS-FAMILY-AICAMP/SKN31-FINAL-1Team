"""
a2_3_assignee_recommend/agent.py

AI 담당자 추천 (FR-05-016, 017)
하이브리드 구조: rule_filter.py(코드)가 후보를 좁히고, LLM은 근거 문장만 생성한다.
"""

import logging
from typing import Any, Dict, List

from pydantic import ValidationError

from shared.llm_client import get_client
from shared.retry_config import DEFAULT_MAX_TOKENS, DEFAULT_MODEL, MAX_RETRIES, TEMPERATURE_STRUCTURED

from .prompt_builder import build_system_prompt
from .rule_filter import filter_candidates
from .schemas import RecommendationList

logger = logging.getLogger(__name__)


def get_project_members(project_id: str) -> List[Dict[str, Any]]:
    """TODO(담당자1): member/assignment 테이블에서 기술스택·현재업무량·이력 조회."""
    raise NotImplementedError


def recommend_assignee(task: Dict[str, Any], members: List[Dict[str, Any]]) -> RecommendationList:
    candidates = filter_candidates(task, members)

    if not candidates:
        # 규칙: 근거 없으면 자동확정 대신 보류
        logger.warning("task_id=%s: 조건을 만족하는 후보가 없어 보류 처리", task["task_id"])
        return RecommendationList(task_id=task["task_id"], recommendations=[], review_required=True)

    client = get_client()
    system_prompt = build_system_prompt(task["task_id"], candidates)

    return client.chat.completions.create(
        model=DEFAULT_MODEL,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=TEMPERATURE_STRUCTURED,
        system=system_prompt,
        messages=[{"role": "user", "content": "위 후보 목록에 대한 추천 근거를 작성하라."}],
        response_model=RecommendationList,
        max_retries=MAX_RETRIES,
    )


def assignee_recommend_node(state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        members = get_project_members(state["project_id"])
    except NotImplementedError:
        return {"error": "NOT_IMPLEMENTED: get_project_members"}

    assignments = []
    for task in state.get("tasks", []):
        try:
            result = recommend_assignee(task, members)
        except ValidationError as e:
            logger.error("A2-3 스키마 검증 실패: %s", e)
            return {"error": f"SCHEMA_VALIDATION_FAILED: {e}"}
        except Exception as e:
            logger.exception("A2-3 실행 중 오류")
            return {"error": f"GENERATION_FAILED: {e}"}
        assignments.append(result.model_dump(mode="json"))

    return {"assignments": assignments, "error": None}

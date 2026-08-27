"""
plan_draft/agent.py

LangGraph 노드 진입점.
구조화 JSON 을 받아 기획서 12개 항목으로 만든다.

이 에이전트는 LLM 을 호출하지 않는다.
매핑 규칙이 문서로 확정돼 있어 코드로 결정적으로 구현할 수 있고,
그 편이 빠르고 비용이 없으며 결과가 흔들리지 않는다.
prompts/ 폴더가 없는 이유도 이것이다.
"""

from __future__ import annotations

import logging
from typing import Any

from meeting_analysis.schemas import PlanDraft

from .renderer import render
from .schemas import PlanDocument

logger = logging.getLogger(__name__)


def generate_plan_document(plan: PlanDraft) -> PlanDocument:
    """구조화 JSON → 기획서 문서."""
    doc = render(plan)

    empty = [s.no for s in doc.sections if s.is_empty]
    if empty:
        logger.info("회의에서 논의되지 않은 항목: %s", empty)

    return doc


def run(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph 노드.

    입력  state["plan_draft"]      meeting_analysis 의 출력
    출력  state["plan_document"]   화면이 그릴 12개 항목
          state["empty_sections"]  비어 있는 항목 번호
    """
    plan = state["plan_draft"]
    if isinstance(plan, dict):
        plan = PlanDraft(**plan)

    doc = generate_plan_document(plan)

    return {
        **state,
        "plan_document": doc.model_dump(mode="json"),
        "empty_sections": [s.no for s in doc.sections if s.is_empty],
    }
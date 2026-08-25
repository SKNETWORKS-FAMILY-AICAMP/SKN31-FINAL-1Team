"""
a2_1_requirement_draft/agent.py

요구사항정의서 초안 생성 (FR-03-006, 007)
반려 시 이 노드로 되돌아온다 (graph.py의 requirement_review_gate 참고).
"""

import logging
from typing import Any, Dict, List

from pydantic import ValidationError

from shared.llm_client import get_client
from shared.retry_config import DEFAULT_MAX_TOKENS, DEFAULT_MODEL, MAX_RETRIES, TEMPERATURE_STRUCTURED

from .prompt_builder import build_messages, load_nfr_checklist
from .schemas import (
    PlanDocument,
    RequirementDocument,
    RequirementDocumentOutput,
    ReqType,
    ReviewStatus,
    Source,
)

logger = logging.getLogger(__name__)


def verify_baseline_coverage(doc: RequirementDocument) -> List[str]:
    """baseline 카테고리(보안성·신뢰성)가 최소 1건씩 생성되었는지 확인."""
    checklist = load_nfr_checklist()
    baseline_names = [
        cat["name_kr"]
        for cat in checklist.get("standard_categories", [])
        if cat["generation_mode"] == "baseline"
    ]
    generated = {
        item.category_1 for item in doc.requirements if item.type == ReqType.NON_FUNCTIONAL
    }
    return [name for name in baseline_names if name not in generated]


def verify_source_consistency(doc: RequirementDocument) -> List[str]:
    return [
        f"{item.id}: baseline 항목이 검토대기가 아님"
        for item in doc.requirements
        if item.source == Source.BASELINE_DEFAULT and item.review_status != ReviewStatus.PENDING
    ]


def generate_requirements(plan: PlanDocument, plan_id: str | None = None) -> RequirementDocumentOutput:
    client = get_client()
    messages = build_messages(plan)
    system_content = messages[0]["content"]
    user_messages = messages[1:]

    doc: RequirementDocument = client.chat.completions.create(
        model=DEFAULT_MODEL,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=TEMPERATURE_STRUCTURED,
        system=system_content,
        messages=user_messages,
        response_model=RequirementDocument,
        max_retries=MAX_RETRIES,
    )

    missing = verify_baseline_coverage(doc)
    if missing:
        logger.warning("baseline 카테고리 누락: %s", ", ".join(missing))
    for problem in verify_source_consistency(doc):
        logger.warning("source 일관성 문제: %s", problem)

    return RequirementDocumentOutput(
        project_id=plan.project_id,
        plan_id=plan_id,
        requirements=doc.requirements,
        review_status=ReviewStatus.PENDING,
    )


def requirement_draft_node(state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        plan = PlanDocument.model_validate(state["plan"])
    except ValidationError as e:
        logger.error("입력 기획서 스키마 검증 실패: %s", e)
        return {"error": f"INVALID_PLAN_INPUT: {e}"}

    try:
        result = generate_requirements(plan, plan_id=state.get("plan_id"))
    except ValidationError as e:
        logger.error("A2-1 스키마 검증 실패(재시도 소진): %s", e)
        return {"error": f"SCHEMA_VALIDATION_FAILED: {e}"}
    except Exception as e:
        logger.exception("A2-1 실행 중 오류")
        return {"error": f"GENERATION_FAILED: {e}"}

    return {"requirement_doc": result.model_dump(mode="json"), "error": None}

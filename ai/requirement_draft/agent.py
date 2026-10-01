"""
a2_1_requirement_draft/agent.py

요구사항정의서 초안 생성 (FR-03-006, 007)
반려 시 이 노드로 되돌아온다 (graph.py의 requirement_review_gate 참고).
"""

import json
import logging
from typing import Any, Dict, List

from pydantic import ValidationError

from shared.llm_client import create_structured, traceable
from shared.retry_config import DEFAULT_MAX_TOKENS, MAX_RETRIES, TEMPERATURE_STRUCTURED

from .prompt_builder import build_messages, load_nfr_checklist
from .quality import collect_requirement_quality_issues, format_quality_issues
from .schemas import (
    ItemReviewStatus,
    PlanDocument,
    RequirementDocument,
    RequirementDocumentOutput,
    RequirementItem,
    ReqType,
    ReviewStatus,
    Source,
)

logger = logging.getLogger(__name__)


def dedupe_requirement_ids(items: List[RequirementItem]) -> List[RequirementItem]:
    """1차 생성 결과와 baseline 재시도 결과를 합칠 때 id가 겹치는 문제를 막는다.

    RequirementDocument.validate_unique_ids는 "한 번의 LLM 호출 결과 안에서"만
    중복을 검사한다 — 1차 호출과 재시도 호출은 서로가 이미 무슨 id를 썼는지
    모르는 채로 각자 만들기 때문에(재시도 프롬프트에 기존 id 목록을 안 넘김),
    둘을 합친 최종 리스트에는 중복이 생길 수 있다(실제로 재현됨: 재시도 후
    RequirementDocument 재검증에서 ValidationError 발생). 여기서 접두어
    (예: "NFR-03")는 유지한 채 같은 접두어 안에서 다음으로 비어있는 일련번호를
    찾아 다시 매긴다 — id 포맷 검증(N?FR-\\d{2}-\\d{3})을 그대로 지키므로 이후
    재검증에도 안전하다. 최초로 나온 id는 그대로 두고, 그다음부터 나오는
    같은 id만 새 번호를 받는다.
    """
    used_ids = {item.id for item in items}
    seen_once: set[str] = set()
    result: List["RequirementItem"] = []
    for item in items:
        if item.id not in seen_once:
            seen_once.add(item.id)
            result.append(item)
            continue
        prefix = item.id.rsplit("-", 1)[0]  # "NFR-03-001" -> "NFR-03"
        seq = 1
        while True:
            candidate = f"{prefix}-{seq:03d}"
            if candidate not in used_ids:
                break
            seq += 1
        used_ids.add(candidate)
        logger.warning("요구사항 ID 중복 발견 — %s를 %s로 재번호 부여", item.id, candidate)
        result.append(item.model_copy(update={"id": candidate}))
    return result


def verify_baseline_coverage(doc: RequirementDocument) -> List[str]:
    """체크리스트의 모든 카테고리(2026-09-08부터 전부 baseline)가 최소 1건씩
    생성되었는지 확인한다.

    NFR 표준 카테고리명(보안성/신뢰성 등)은 category_2에 들어간다 —
    category_1은 "기능"/"비기능" 두 값뿐이라(schemas.py의 validate_consistency
    참고) 여기서 category_1을 보면 전부 "비기능"으로만 잡혀서 커버리지 확인이
    항상 무의미해진다. standard_categories와 project_specific_categories
    둘 다 확인한다 — 전부 baseline으로 바뀌면서 AI 특화 카테고리도 최소 1건
    보장 대상에 들어갔다.
    """
    checklist = load_nfr_checklist()
    all_categories = checklist.get("standard_categories", []) + checklist.get(
        "project_specific_categories", []
    )
    baseline_names = [cat["name_kr"] for cat in all_categories if cat["generation_mode"] == "baseline"]
    generated = {
        item.category_2 for item in doc.requirements if item.type == ReqType.NON_FUNCTIONAL
    }
    return [name for name in baseline_names if name not in generated]


def verify_source_consistency(doc: RequirementDocument) -> List[str]:
    """baseline_default 항목은 항상 검토대기여야 한다는 규칙이 실제로
    지켜졌는지 확인한다. item.review_status는 문서 단위 게이트(ReviewStatus)가
    아니라 항목 단위 확신도(ItemReviewStatus)라 그쪽으로 비교해야 한다."""
    return [
        f"{item.id}: baseline 항목이 검토대기가 아님"
        for item in doc.requirements
        if item.source == Source.BASELINE_DEFAULT
        and item.review_status != ItemReviewStatus.PENDING
    ]


def merge_quality_replacements(
    items: List[RequirementItem],
    replacements: List[RequirementItem],
    invalid_ids: set[str],
) -> List[RequirementItem]:
    """Replace only rejected items while preserving document order and valid items."""
    replacement_by_id = {
        item.id: item for item in replacements if item.id in invalid_ids
    }
    return [
        replacement_by_id.get(item.id, item) if item.id in invalid_ids else item
        for item in items
    ]


def finalize_unresolved_quality_items(
    items: List[RequirementItem], quality_issues
) -> List[RequirementItem]:
    """Apply a conservative final fallback after LLM correction retries.

    Ungrounded or invented requirements are removed because saving them would
    turn a proposal into project scope. Items whose only remaining problem is
    acceptance wording keep their grounded content, become review-pending, and
    receive an objective test condition without inventing a numeric threshold.
    """
    codes_by_id: dict[str, set[str]] = {}
    for issue in quality_issues:
        codes_by_id.setdefault(issue.requirement_id, set()).add(issue.code)

    result: List[RequirementItem] = []
    for item in items:
        codes = codes_by_id.get(item.id, set())
        if not codes:
            result.append(item)
            continue
        if "UNSUPPORTED_DESIGN" in codes or any(
            code.startswith("EVIDENCE_") for code in codes
        ):
            logger.warning("근거 미충족 요구사항 제거: %s (%s)", item.id, sorted(codes))
            continue
        if all(code.startswith("ACCEPTANCE_") for code in codes):
            if item.type == ReqType.FUNCTIONAL:
                criteria = (
                    f"대표 입력으로 '{item.title}' 기능을 실행했을 때 description에 "
                    "명시된 출력 또는 상태 변경이 발생하는지 기능 테스트로 확인한다."
                )
            else:
                criteria = (
                    f"'{item.title}' 조건을 재현한 시험에서 description에 명시된 "
                    "품질 특성이 유지되는지 테스트 결과와 로그로 확인한다."
                )
            note = f"{item.note} | 자동 품질 보정된 인수조건은 PM 확인 필요"
            result.append(
                item.model_copy(
                    update={
                        "acceptance_criteria": criteria,
                        "review_status": ItemReviewStatus.PENDING,
                        "note": note,
                    }
                )
            )
            continue
        result.append(item)
    return result


@traceable(name="requirement_draft.generate_requirements")
def generate_requirements(plan: PlanDocument, plan_id: str | None = None, on_stage=None) -> RequirementDocumentOutput:
    # on_stage: 있으면 각 내부 단계 시작 시 사람이 읽을 라벨(str)로 호출한다(선택,
    # 2026-09-15 — 업무 배분/기획서 생성과 같은 진행 표시를 요구사항정의서
    # 생성에도 추가하기 위해 도입).
    def _stage(label: str) -> None:
        if on_stage:
            on_stage(label)

    messages = build_messages(plan)
    system_prompt = messages[0]["content"]
    user_message = messages[1]["content"]

    _stage("요구사항 초안 생성 중…")
    doc: RequirementDocument = create_structured(
        system_prompt=system_prompt,
        user_message=user_message,
        response_model=RequirementDocument,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=TEMPERATURE_STRUCTURED,
        max_retries=MAX_RETRIES,
    )
    all_items = list(doc.requirements)

    # baseline NFR 카테고리가 빠지면, 예전엔 로그만 남기고 그대로 넘어갔다
    # (2026-09-08 이전). task_generation의 요구사항 커버리지 재시도와 같은
    # 이유로 — "누락됐다"는 사실을 로그로만 남기면 아무도 안 보는 채로
    # 불완전한 문서가 그대로 나간다 — 빠진 카테고리만 콕 집어 재요청하고
    # 기존 결과에 병합하는 재시도를 추가한다. 이미 만든 항목은 다시
    # 만들지 않고(재요청 메시지에 명시), 빠진 것만 추가로 받는다.
    for attempt in range(MAX_RETRIES):
        missing = verify_baseline_coverage(RequirementDocument(requirements=all_items))
        if not missing:
            break
        logger.warning(
            "baseline 카테고리 누락(재시도 %d/%d): %s", attempt + 1, MAX_RETRIES, ", ".join(missing)
        )
        _stage(f"누락 카테고리 보완 중… ({attempt + 1}/{MAX_RETRIES})")
        retry_message = (
            f"{user_message}\n\n"
            f"방금 생성한 결과에 다음 비기능요구사항 카테고리가 하나도 없다: {missing}. "
            f"이 카테고리들에 대해서만 각각 최소 1건씩 요구사항을 새로 생성하라. "
            f"이미 만든 다른 항목이나 기능요구사항은 다시 만들지 마라."
        )
        try:
            retry_doc: RequirementDocument = create_structured(
                system_prompt=system_prompt,
                user_message=retry_message,
                response_model=RequirementDocument,
                max_tokens=DEFAULT_MAX_TOKENS,
                temperature=TEMPERATURE_STRUCTURED,
                max_retries=MAX_RETRIES,
            )
        except Exception as e:
            logger.warning("baseline 재시도 호출 실패(재시도 %d/%d): %s", attempt + 1, MAX_RETRIES, e)
            continue
        # 재시도 호출은 1차 호출이 이미 쓴 id를 모르는 채로 새로 만들기 때문에, 합친
        # 리스트에는 중복이 생길 수 있다 — 다음 줄의 재검증(RequirementDocument 재생성)이
        # 그 중복을 걸러내기 전에 먼저 재번호를 매겨 통과하게 한다.
        all_items = dedupe_requirement_ids(all_items + list(retry_doc.requirements))

    # Retry only rejected items so corrections do not destabilize valid output.
    for attempt in range(MAX_RETRIES):
        quality_issues = collect_requirement_quality_issues(plan, all_items)
        if not quality_issues:
            break
        invalid_ids = {issue.requirement_id for issue in quality_issues}
        invalid_items = [
            item.model_dump(mode="json") for item in all_items if item.id in invalid_ids
        ]
        logger.warning(
            "요구사항 품질 검증 실패(재시도 %d/%d): %s",
            attempt + 1,
            MAX_RETRIES,
            ", ".join(sorted(invalid_ids)),
        )
        _stage(f"요구사항 품질 보완 중… ({attempt + 1}/{MAX_RETRIES})")
        retry_message = (
            f"{user_message}\n\n"
            "아래 요구사항만 품질 검증에 실패했다. ID를 바꾸지 말고 실패 항목만 "
            "수정하여 requirements 배열로 반환하라. 다른 ID의 항목은 반환하지 마라.\n"
            "UNSUPPORTED_DESIGN 오류의 용어와 그 용어에 의존하는 설계는 완전히 제거하라. "
            "ACCEPTANCE 오류는 '후속 확정', '미정', 주관적 표현을 쓰지 말고, 기획서에 "
            "없는 수치를 만들지 않으면서 실행 조건·관찰 가능한 결과·시험 방법을 모두 "
            "포함한 통과/실패 조건으로 다시 작성하라.\n"
            f"[검증 오류]\n{format_quality_issues(quality_issues)}\n"
            f"[수정 대상]\n{json.dumps(invalid_items, ensure_ascii=False, indent=2)}"
        )
        try:
            retry_doc: RequirementDocument = create_structured(
                system_prompt=system_prompt,
                user_message=retry_message,
                response_model=RequirementDocument,
                max_tokens=DEFAULT_MAX_TOKENS,
                temperature=TEMPERATURE_STRUCTURED,
                max_retries=MAX_RETRIES,
            )
        except Exception as e:
            logger.warning(
                "품질 보완 호출 실패(재시도 %d/%d): %s",
                attempt + 1,
                MAX_RETRIES,
                e,
            )
            continue
        all_items = merge_quality_replacements(
            all_items, list(retry_doc.requirements), invalid_ids
        )

    quality_issues = collect_requirement_quality_issues(plan, all_items)
    if quality_issues:
        _stage("미해결 품질 항목 보수적 처리 중…")
        all_items = finalize_unresolved_quality_items(all_items, quality_issues)

    _stage("최종 검증 중…")
    remaining = verify_baseline_coverage(RequirementDocument(requirements=all_items))
    if remaining:
        logger.error("재시도 소진 — baseline 카테고리 여전히 누락: %s", ", ".join(remaining))
    for problem in verify_source_consistency(RequirementDocument(requirements=all_items)):
        logger.warning("source 일관성 문제: %s", problem)
    quality_issues = collect_requirement_quality_issues(plan, all_items)
    if quality_issues:
        raise ValueError(
            "요구사항 품질 검증을 통과하지 못했습니다:\n"
            + format_quality_issues(quality_issues)
        )

    return RequirementDocumentOutput(
        project_id=plan.project_id,
        plan_id=plan_id,
        requirements=all_items,
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
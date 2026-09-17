import json

from shared.llm_client import create_structured
from shared.retry_config import MAX_RETRIES, MAX_TOKENS, MODEL, TEMPERATURE
from .schemas import RequirementReviewResult


SYSTEM_PROMPT = """당신은 소프트웨어 요구사항 품질 감사자입니다.
기획서를 유일한 사실 원천으로 삼아 요구사항정의서의 정확성, 완전성, 일관성, 테스트 가능성을 각각 0~100점으로 평가하세요.
기획서에 없는 기능을 만들지 마세요. 누락된 기획서 기능은 요구사항으로 보완하세요.
모호한 표현은 입력·처리·출력과 검증 가능한 수용 기준을 갖도록 구체화하세요.
revised_items에는 보완사항을 실제 반영한 전체 요구사항 목록을 반환해야 하며 기존 코드는 가능한 한 유지하세요.
verdict는 pass, needs_improvement, critical 중 하나만 사용하세요."""


def run(plan_document: dict, requirement_items: list[dict]) -> RequirementReviewResult:
    return create_structured(
        system_prompt=SYSTEM_PROMPT,
        user_message=(
            "[기획서]\n" + json.dumps(plan_document, ensure_ascii=False) +
            "\n\n[검토 대상 요구사항정의서]\n" + json.dumps(requirement_items, ensure_ascii=False)
        ),
        response_model=RequirementReviewResult,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        max_retries=MAX_RETRIES,
        openai_model=MODEL,
    )

from shared.llm_client import create_structured
from shared.retry_config import MAX_RETRIES, MAX_TOKENS, MODEL, TEMPERATURE
from .schemas import PlanReviewResult


SYSTEM_PROMPT = """당신은 IT 기획서 품질 감사자입니다. 회의록만을 유일한 사실 원천으로 삼아 기획서를 검증하세요.
정확성(사실 일치), 완전성(논의 내용 누락), 일관성(문서 내부 모순), 추적가능성(근거 존재)을 각각 0~100점으로 엄격히 평가합니다.
회의록에 없는 내용을 그럴듯하게 만들지 마세요. evidence에는 회의록에 실제 존재하는 짧은 문구만 넣으세요.
7개 section_key는 overview, problem_definition, goals, target_users, key_features, tech_stack, final_decisions입니다.
revised_document는 기존 기획서를 보완한 전체 새 버전입니다. 각 필드는 반드시 기존 양식과 같은 제한 HTML로 작성하세요.
문단은 <p>, 목록은 <ul><li>, 강조는 <strong>만 사용하며 줄바꿈 없는 번호 나열은 금지합니다.
근거가 없는 기존 주장은 삭제하거나 '회의에서 논의되지 않았습니다.'로 표시하세요.
verdict는 pass, needs_improvement, critical 중 하나만 사용하세요."""


def run(meeting_text: str, document: dict) -> PlanReviewResult:
    labels = {
        "overview": "프로젝트 개요", "problem_definition": "핵심 목표",
        "goals": "세부 목표 및 문제 정의", "target_users": "대상 사용자",
        "key_features": "주요 기능", "tech_stack": "기술 스택 및 제약사항",
        "final_decisions": "최종 결정사항",
    }
    body = "\n\n".join(f"[{labels[k]} / {k}]\n{document.get(k) or ''}" for k in labels)
    return create_structured(
        system_prompt=SYSTEM_PROMPT,
        user_message=f"[회의록]\n{meeting_text}\n\n[검토 대상 기획서]\n{body}",
        response_model=PlanReviewResult,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        max_retries=MAX_RETRIES,
        openai_model=MODEL,
    )

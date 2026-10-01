import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from shared.llm_client import build_chat_kwargs

from .eligibility_prompt import (
    build_messages,
    build_paragraph_messages,
    number_paragraphs,
)


class MeetingEligibilityError(Exception):
    """회의록 관련성 판정으로 기획서 생성이 중단된 경우."""

    def __init__(self, message: str, cause_code: str):
        super().__init__(message)
        self.cause_code = cause_code


class MeetingRelevance(BaseModel):
    """
    1단계 판정 결과. 원문 발췌를 받지 않습니다.

    2026-09-14: 관련성 판정을 두 단계로 나눴습니다.

    예전에는 한 번에 status와 relevant_passages를 같이 받았습니다.
    그런데 relevant 판정에서는 발췌를 쓰지 않고 원문을 그대로
    전달합니다(validate_relevant_passages 참고). 쓰지도 않는 발췌를
    모델이 복창하느라 출력이 회의록 길이에 비례해 커졌고,
    긴 회의록에서 출력 상한(gpt-4o는 16384)을 넘겨 500이 났습니다.

        IncompleteOutputException: The output is incomplete
        due to a max_tokens length limit.

    토큰 상한을 올리는 것으로는 못 고칩니다. 16384가 모델의 최대이고,
    회의록이 길어지면 언제든 다시 넘습니다. 출력 크기가 입력 크기에
    비례하지 않게 만들어야 합니다.

    이 스키마에는 발췌 필드가 없으므로 출력이 회의록 길이와 무관하게
    짧습니다. 발췌가 실제로 필요한 mixed 판정에서만 2단계로
    MeetingEligibility를 다시 받습니다.
    """

    status: Literal[
        "relevant",
        "mixed",
        "irrelevant",
        "needs_clarification",
    ]

    reason: str = Field(
        min_length=1,
        description="회의 원문을 근거로 작성한 판정 이유",
    )

    @model_validator(mode="after")
    def strip_reason(self):
        self.reason = self.reason.strip()

        if not self.reason:
            raise ValueError("판정 이유가 비어 있습니다.")

        return self


class RelevantParagraphs(BaseModel):
    """
    mixed 2단계 응답. 개발 관련 문단의 번호만 받습니다.

    2026-09-14: 발췌 전문 대신 번호를 받도록 바꿨습니다.
    이유는 eligibility_prompt.PARAGRAPH_SYSTEM_PROMPT 위 주석을 보십시오.

    번호만 오므로 출력이 회의록 길이와 무관하고, 원문은 코드가 잘라내므로
    모델이 글자를 바꿀 수 없습니다.
    """

    paragraph_numbers: list[int] = Field(
        default_factory=list,
        description="개발 기획과 관련된 문단의 번호",
    )


class MeetingEligibility(BaseModel):
    """회의록의 개발 관련성 판정 결과."""

    status: Literal[
        "relevant",
        "mixed",
        "irrelevant",
        "needs_clarification",
    ]

    reason: str = Field(
        min_length=1,
        description="회의 원문을 근거로 작성한 판정 이유",
    )

    relevant_passages: list[str] = Field(
        default_factory=list,
        description="개발 관련 회의 원문 발췌",
    )

    # 코드가 채우는 필드입니다. LLM 응답 스키마에 노출되지만
    # 프롬프트에서 요구하지 않으므로 모델은 비워 둡니다.
    #
    # 2026-09-14: relevant 판정에서 원문 대조에 실패한 발췌를 기록합니다.
    # 이 경로는 발췌를 하류에 쓰지 않으므로 생성을 중단하지 않지만,
    # 판정 근거를 확인하지 못했다는 사실 자체는 남겨야 합니다.
    unverified_passages: list[str] = Field(
        default_factory=list,
        exclude=True,
        description="원문에서 확인하지 못한 발췌. 코드가 채웁니다.",
    )

    @model_validator(mode="after")
    def validate_result(self):
        self.reason = self.reason.strip()

        allowed = self.status in {
            "relevant",
            "mixed",
        }

        # 2026-09-14: 발췌를 필수로 요구하는 것은 mixed뿐입니다.
        # mixed는 발췌가 곧 하류 입력이라 없으면 진행할 수 없지만,
        # relevant는 원문을 그대로 전달하므로 발췌가 없어도 됩니다.
        if self.status == "mixed" and not self.relevant_passages:
            raise ValueError(
                "mixed 판정에는 개발 관련 원문 발췌가 필요합니다."
            )

        if not allowed and self.relevant_passages:
            raise ValueError(
                "중단 판정에는 관련 원문 발췌를 넣을 수 없습니다."
            )

        if any(
            not passage.strip()
            for passage in self.relevant_passages
        ):
            raise ValueError(
                "빈 원문 발췌는 허용되지 않습니다."
            )

        return self


def find_original_passage(
    passage: str,
    meeting_text: str,
    start_position: int = 0,
):
    """
    모델이 발췌문의 공백이나 줄바꿈을 합친 경우에도
    원문에서 같은 문장을 찾아 실제 원문 구간을 반환합니다.

    단어, 숫자와 문장부호는 그대로 일치해야 합니다.
    공백과 줄바꿈 차이만 허용합니다.
    """

    words = passage.strip().split()

    if not words:
        return None

    pattern = r"\s+".join(
        re.escape(word)
        for word in words
    )

    return re.search(
        pattern,
        meeting_text[start_position:],
    )


def find_unused_passage(
    passage: str,
    meeting_text: str,
    used_spans: list[tuple[int, int]],
):
    """
    아직 쓰지 않은 원문 구간에서 발췌문을 찾습니다.

    ## 왜 순서를 요구하지 않는가

    2026-09-14 변경: 예전에는 커서를 앞으로만 전진시키며 찾았습니다.
    그러면 모델이 발췌문을 원문 순서대로 내놓지 않을 때 뒤쪽에서
    찾지 못해 판정 전체가 실패했습니다.

    긴 회의록일수록 발췌가 많아지고(실측 23건), 그중 하나만 순서가
    어긋나도 전부 실패합니다. 실제로 meeting_note_3_long에서
    재현됐습니다. 발췌 순서는 모델이 통제하는 값인데 그것에
    파이프라인 성공 여부를 걸 이유가 없습니다.

    중복 선택을 막는 것이 커서의 본래 목적이므로, 순서 대신
    이미 사용한 구간과 겹치는지로 판단합니다.
    """
    search_from = 0

    while True:
        match = find_original_passage(
            passage=passage,
            meeting_text=meeting_text,
            start_position=search_from,
        )

        if match is None:
            return None

        start = search_from + match.start()
        end = search_from + match.end()

        overlaps = any(
            start < used_end and used_start < end
            for used_start, used_end in used_spans
        )

        if not overlaps:
            return start, end

        # 겹치면 그다음 위치부터 다시 찾습니다.
        search_from = start + 1


def validate_relevant_passages(
    result: MeetingEligibility,
    meeting_text: str,
) -> str:
    """
    판정 근거를 검증하고 구조화 단계에 전달할 원문을 반환합니다.

    relevant:
        회의 전체가 개발 기획과 관련된 경우입니다.
        발췌문은 판정 근거 확인에만 사용하고 전체 원문을 전달합니다.

    mixed:
        개발 논의와 무관한 논의가 섞인 경우입니다.
        검증된 개발 관련 발췌문만 전달합니다.
    """
    if result.status == "irrelevant":
        raise MeetingEligibilityError(
            (
                "개발 기획과 관련된 회의 내용이 확인되지 않아 "
                f"기획서를 생성하지 않았습니다. {result.reason}"
            ),
            cause_code="MEETING_NOT_RELEVANT",
        )

    if result.status == "needs_clarification":
        raise MeetingEligibilityError(
            (
                "개발 대상과 논의 내용을 더 구체적으로 입력해 주세요. "
                f"기획서 생성을 보류했습니다. {result.reason}"
            ),
            cause_code="MEETING_NEEDS_CLARIFICATION",
        )

    if not meeting_text.strip():
        raise MeetingEligibilityError(
            "개발 관련성을 확인할 회의 원문이 필요합니다.",
            cause_code="MEETING_ELIGIBILITY_INVALID",
        )

    # 2026-09-14: relevant는 발췌를 요구하지 않게 바뀌었습니다.
    # 1단계 판정만으로 원문을 그대로 전달합니다(MeetingRelevance 참고).
    # 발췌가 있으면 판정 근거로 대조는 하되, 없다고 중단하지 않습니다.
    if result.status == "mixed" and not result.relevant_passages:
        raise MeetingEligibilityError(
            "개발 관련 내용으로 선택된 문장이 없습니다. 다시 분석해 주세요.",
            cause_code="MEETING_ELIGIBILITY_INVALID",
        )

    # relevant 판정도 근거 검증을 생략하지 않습니다.
    # 실제로 존재하는 원문인지 확인합니다.
    #
    # 2026-09-14: 발췌 "순서"는 더 이상 요구하지 않습니다.
    # 순서는 모델이 정하는 값인데, 어긋나면 판정 전체가 실패했습니다
    # (find_unused_passage 참고). 중복 선택 방지는 그대로 유지합니다.
    verified_spans: list[tuple[int, int]] = []
    unverified: list[str] = []

    for passage in result.relevant_passages:
        span = find_unused_passage(
            passage=passage,
            meeting_text=meeting_text,
            used_spans=verified_spans,
        )

        if span is None:
            unverified.append(passage)
            continue

        verified_spans.append(span)

    if result.status == "relevant":
        # 전체가 관련 회의라면 발췌 과정에서 배경과 문제를 잃지 않도록
        # 원본 문자열을 그대로 전달합니다.
        #
        # 2026-09-14: 이 경로에서는 발췌 결과를 쓰지 않습니다. 그래서
        # 근거 대조에 실패해도 생성을 중단하지 않습니다. 쓰이지도 않는
        # 검증 때문에 기획서를 못 만드는 것은 실패 비용이 과합니다.
        # 대조 실패 사실은 호출부가 확인할 수 있도록 남깁니다.
        result.unverified_passages = unverified
        return meeting_text

    # mixed 판정에서는 전체 원문을 전달하지 않습니다.
    # 회식 등 무관한 내용이 제외된 원문 구간만 전달합니다.
    #
    # 이 경로는 발췌 결과가 곧 하류 입력이므로 근거 검증이 필수입니다.
    # 확인하지 못한 발췌가 있으면 중단합니다.
    if unverified:
        raise MeetingEligibilityError(
            (
                "개발 관련 내용으로 선택된 문장을 회의록 원문에서 "
                "확인하지 못했습니다. 다시 분석해 주세요."
            ),
            cause_code="MEETING_ELIGIBILITY_INVALID",
        )

    if not verified_spans:
        raise MeetingEligibilityError(
            (
                "개발 관련 내용으로 선택된 문장을 회의록 원문에서 "
                "확인하지 못했습니다. 다시 분석해 주세요."
            ),
            cause_code="MEETING_ELIGIBILITY_INVALID",
        )

    return "\n\n".join(
        meeting_text[start:end]
        for start, end in sorted(verified_spans)
    )

# 고른 문단의 앞뒤로 코드가 무조건 끌어올 문단 수.
#
# 2026-09-14: 실제 회의 전사본에서 모델이 고른 문단만 넘겼더니
# 기술 스택 논의가 통째로 빠졌습니다. 대화에서는 근거와 결론이
# 다른 발언에 나뉘어 있습니다 — "런팟으로 GPU를 빌려서"와
# "A100은 쓰라고 하더라고요"가 서로 다른 줄입니다. 당시엔 코드가
# 앞뒤 1개를 무조건 끌어와 보정했습니다(CONTEXT_PARAGRAPHS=1).
#
# 2026-09-16: 그 무조건 확장이 무관한 이웃까지 끌어오는 걸 실측으로
# 재현했습니다 — 29,769자 실제 회의록 중간에 잡담 블록을 넣고 6회
# 반복 호출한 결과, 개발 논의 문단 바로 다음에 잡담이 이어지면 모델이
# 잡담 문단을 단 한 번도 직접 고르지 않았는데도 6번 중 3번 relevant_text에
# 새어 들어갔습니다. 순전히 "이웃이라서" 끌려온 것입니다.
#
# 길이 등 문단 자체의 특징으로 "이어지는 말"과 "다른 주제"를 구분해
# 보려 했으나 실측에서 기각했습니다 — 같은 회의록에서 무관한 문단
# (34~56자)이 실제 개발 논의 문단(97~181자)보다 오히려 짧아, 길이가
# 주제 연관성과 상관이 없었습니다(파일 상단 커밋 로그 참고).
#
# 이제 "바로 앞뒤 문단이 같은 발언의 연속인가"라는 판단은 코드의 맹목적
# 확장이 아니라 모델에게 맡깁니다(eligibility_prompt.PARAGRAPH_SYSTEM_PROMPT
# 참고 — 포함할 것에 "이어지는 문맥", 제외할 것에 "인접해도 다른 주제로
# 넘어간 문단"을 명시). 이건 원문 대조처럼 코드가 검증할 수 있는 사실이
# 아니라 의미 판단이라, 다른 항목들과 달리 모델의 판단 자체가 유일한
# 근거입니다. CONTEXT_PARAGRAPHS는 남겨두되 0으로 낮춰 코드가 더 이상
# 무관한 이웃을 강제로 끼워 넣지 않게 합니다.
#
# 실측(같은 잡담 주입 시나리오, 프롬프트 수정 후 6회 반복)으로 확인:
# 잡담 누출 0/6, 그리고 원래 CONTEXT_PARAGRAPHS=1이 보정하던 실제 개발
# 논의 문단(133~136, 147번 등 인접한 여러 문단)도 모델이 직접 전부
# 선택해 코드 쪽 보정 없이도 빠짐이 없었습니다.
CONTEXT_PARAGRAPHS = 0


def select_paragraphs(
    numbered: list[tuple[int, str]],
    numbers: list[int],
    context: int = CONTEXT_PARAGRAPHS,
) -> list[str]:
    """모델이 고른 번호로 원문 문단을 잘라낸다.

    모델이 범위 밖 번호나 중복을 낼 수 있으므로 코드가 거릅니다.
    고른 문단의 앞뒤 context개를 함께 가져와 맥락을 보존합니다.
    원문 순서를 유지합니다 — 회의 흐름이 뒤섞이면 하류가 배경과
    결정의 선후를 잘못 읽습니다.
    """
    by_number = dict(numbered)
    picked: set[int] = set()

    for number in numbers:
        if not isinstance(number, int):
            continue

        if number not in by_number:
            continue

        for offset in range(-context, context + 1):
            neighbour = number + offset

            if neighbour in by_number:
                picked.add(neighbour)

    return [by_number[number] for number in sorted(picked)]


def assess_meeting(
    client,
    meeting_text: str,
    glossary_text: str = "",
    *,
    model: str,
    max_retries: int,
    temperature: float,
    max_tokens: int,
) -> tuple[MeetingEligibility, str]:
    """회의록의 개발 관련성을 판단합니다."""

    if not meeting_text.strip():
        raise MeetingEligibilityError(
            "회의록 내용이 비어 있습니다. 회의 내용을 입력해 주세요.",
            cause_code="MEETING_NEEDS_CLARIFICATION",
        )

    # 2026-09-14: 이 호출만 create()에 인자를 직접 넘기고 있었습니다.
    # 토큰 상한을 주지 않아 API 기본값이 적용됐고, 긴 회의록에서
    # relevant_passages(원문 발췌)를 다 못 쓰고 잘려
    # IncompleteOutputException으로 500이 났습니다.
    #
    # 추출 호출(node.py)처럼 build_chat_kwargs를 쓰면
    #   · 상한을 MAX_TOKENS로 명시하고
    #   · 모델 계열에 맞는 인자 이름(max_tokens / max_completion_tokens)을 고르며
    #   · temperature를 안 받는 추론 모델에서는 자동으로 생략합니다.
    messages = build_messages(
        meeting_text=meeting_text,
        glossary_text=glossary_text,
    )

    def call(response_model):
        return client.chat.completions.create(
            **build_chat_kwargs(
                model=model,
                messages=messages,
                response_model=response_model,
                max_tokens=max_tokens,
                max_retries=max_retries,
                temperature=temperature,
            )
        )

    # ── 1단계: 판정만 받습니다 ────────────────────────────
    # 출력이 status와 reason뿐이라 회의록이 아무리 길어도 짧습니다.
    relevance = call(MeetingRelevance)

    if relevance.status in {"irrelevant", "needs_clarification"}:
        # 중단 판정은 발췌가 필요 없습니다. 그대로 검증기로 넘겨
        # 기존 예외와 메시지를 그대로 씁니다.
        result = MeetingEligibility(
            status=relevance.status,
            reason=relevance.reason,
        )

    elif relevance.status == "relevant":
        # 회의 전체가 관련 내용이면 원문을 그대로 전달합니다.
        # 발췌를 쓰지 않으므로 2단계 호출을 하지 않습니다.
        result = MeetingEligibility(
            status="relevant",
            reason=relevance.reason,
        )

    else:
        # ── 2단계: mixed일 때만 개발 관련 구간을 고릅니다 ──
        # 발췌 전문이 아니라 문단 번호를 받습니다. 출력이 회의록
        # 길이에 비례하지 않게 하려는 것입니다.
        numbered = number_paragraphs(meeting_text)

        chosen = client.chat.completions.create(
            **build_chat_kwargs(
                model=model,
                messages=build_paragraph_messages(numbered),
                response_model=RelevantParagraphs,
                max_tokens=max_tokens,
                max_retries=max_retries,
                temperature=temperature,
            )
        )

        selected = select_paragraphs(
            numbered=numbered,
            numbers=chosen.paragraph_numbers,
        )

        if not selected:
            raise MeetingEligibilityError(
                (
                    "개발 관련 내용으로 선택된 문단이 없습니다. "
                    "다시 분석해 주세요."
                ),
                cause_code="MEETING_ELIGIBILITY_INVALID",
            )

        return (
            MeetingEligibility(
                status="mixed",
                reason=relevance.reason,
                relevant_passages=selected,
            ),
            "\n\n".join(selected),
        )

    relevant_text = validate_relevant_passages(
        result=result,
        meeting_text=meeting_text,
    )

    return result, relevant_text
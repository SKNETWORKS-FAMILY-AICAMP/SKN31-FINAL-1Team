import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from shared.llm_client import build_chat_kwargs

from .eligibility_prompt import build_messages


class MeetingEligibilityError(Exception):
    """회의록 관련성 판정으로 기획서 생성이 중단된 경우."""

    def __init__(self, message: str, cause_code: str):
        super().__init__(message)
        self.cause_code = cause_code


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

        if allowed and not self.relevant_passages:
            raise ValueError(
                "통과 판정에는 개발 관련 원문 발췌가 필요합니다."
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

    if (
        not meeting_text.strip()
        or not result.relevant_passages
    ):
        raise MeetingEligibilityError(
            "개발 관련성을 확인할 회의 원문과 판정 근거가 필요합니다.",
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
    result = client.chat.completions.create(
        **build_chat_kwargs(
            model=model,
            messages=build_messages(
                meeting_text=meeting_text,
                glossary_text=glossary_text,
            ),
            response_model=MeetingEligibility,
            max_tokens=max_tokens,
            max_retries=max_retries,
            temperature=temperature,
        )
    )

    relevant_text = validate_relevant_passages(
        result=result,
        meeting_text=meeting_text,
    )

    return result, relevant_text
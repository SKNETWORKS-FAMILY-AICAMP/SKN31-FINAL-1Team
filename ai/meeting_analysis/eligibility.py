import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

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
    start_position: int,
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

    selected_passages = []
    cursor = 0

    # relevant 판정도 근거 검증을 생략하지 않습니다.
    # 실제로 존재하는 원문인지, 발췌 순서가 올바른지 확인합니다.
    for passage in result.relevant_passages:
        match = find_original_passage(
            passage=passage,
            meeting_text=meeting_text,
            start_position=cursor,
        )

        if match is None:
            raise MeetingEligibilityError(
                (
                    "개발 관련 내용으로 선택된 문장을 회의록 원문에서 "
                    "확인하지 못했습니다. 다시 분석해 주세요."
                ),
                cause_code="MEETING_ELIGIBILITY_INVALID",
            )

        start = cursor + match.start()
        end = cursor + match.end()

        selected_passages.append(
            meeting_text[start:end]
        )
        cursor = end

    if result.status == "relevant":
        # 전체가 관련 회의라면 발췌 과정에서 배경과 문제를 잃지 않도록
        # 원본 문자열을 그대로 전달합니다.
        return meeting_text

    # mixed 판정에서는 전체 원문을 전달하지 않습니다.
    # 회식 등 무관한 내용이 제외된 원문 구간만 전달합니다.
    return "\n\n".join(selected_passages)

def assess_meeting(
    client,
    meeting_text: str,
    glossary_text: str = "",
    *,
    model: str,
    max_retries: int,
    temperature: float,
) -> tuple[MeetingEligibility, str]:
    """회의록의 개발 관련성을 판단합니다."""

    if not meeting_text.strip():
        raise MeetingEligibilityError(
            "회의록 내용이 비어 있습니다. 회의 내용을 입력해 주세요.",
            cause_code="MEETING_NEEDS_CLARIFICATION",
        )

    result = client.chat.completions.create(
        model=model,
        response_model=MeetingEligibility,
        max_retries=max_retries,
        temperature=temperature,
        messages=build_messages(
            meeting_text=meeting_text,
            glossary_text=glossary_text,
        ),
    )

    relevant_text = validate_relevant_passages(
        result=result,
        meeting_text=meeting_text,
    )

    return result, relevant_text
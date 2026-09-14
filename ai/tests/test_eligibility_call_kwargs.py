"""
assess_meeting이 LLM을 부를 때 토큰 상한을 넘기는지 검사합니다.

## 왜 필요한가

2026-09-14 운영 중 500이 났습니다.

    IncompleteOutputException: The output is incomplete
    due to a max_tokens length limit.

노드 1의 두 호출 중 추출 호출만 build_chat_kwargs를 쓰고 있었고,
관련성 판정 호출은 create()에 인자를 직접 넘기면서 토큰 상한을
빠뜨렸습니다. API 기본값이 적용돼서, 회의록이 길면
relevant_passages(원문 발췌)를 다 쓰지 못하고 잘렸습니다.

짧은 회의록에서는 재현되지 않아 테스트로 고정합니다.
LLM을 부르지 않습니다.
"""

import pytest

from meeting_analysis.eligibility_prompt import (
    SHORT_LINE_CHARS,
    number_paragraphs,
)
from meeting_analysis.eligibility import (
    MeetingEligibility,
    MeetingEligibilityError,
    MeetingRelevance,
    RelevantParagraphs,
    assess_meeting,
    select_paragraphs,
)


MEETING = "로그인 기능을 추가하기로 했다. 인증은 JWT를 사용한다."


class _RecordingClient:
    """create()에 들어온 인자를 기록하는 가짜 클라이언트.

    2026-09-14: 판정이 두 단계가 되면서 호출이 여러 번 올 수 있습니다.
    response_model에 맞는 결과를 돌려주고, 호출 인자를 모두 모읍니다.
    """

    def __init__(self, status="relevant", numbers=(1,)):
        self._status = status
        self._numbers = list(numbers)
        self.calls: list[dict] = []
        self.chat = self  # client.chat.completions.create 형태를 흉내냅니다.
        self.completions = self

    @property
    def captured(self) -> dict:
        """마지막 호출 인자. 기존 테스트 호환용입니다."""
        return self.calls[-1] if self.calls else {}

    def create(self, **kwargs):
        self.calls.append(kwargs)
        model = kwargs.get("response_model")

        if model is MeetingRelevance:
            return MeetingRelevance(
                status=self._status,
                reason="개발 관련 회의입니다.",
            )

        if model is RelevantParagraphs:
            return RelevantParagraphs(
                paragraph_numbers=self._numbers
            )

        return MeetingEligibility(
            status=self._status,
            reason="개발 관련 회의입니다.",
            relevant_passages=[MEETING],
        )


def _client(status="relevant", numbers=(1,)):
    return _RecordingClient(status, numbers)


def test_token_limit_is_sent():
    """토큰 상한을 명시해야 긴 회의록에서 출력이 잘리지 않습니다."""
    client = _client()

    assess_meeting(
        client=client,
        meeting_text=MEETING,
        model="gpt-4o",
        max_retries=3,
        temperature=0.0,
        max_tokens=16384,
    )

    # 상한이 실제로 실려야 합니다. 인자 이름은 모델 프로필이 정합니다
    # (현재 모든 프로필이 max_completion_tokens를 씁니다).
    assert client.captured.get("max_completion_tokens") == 16384


def test_token_param_name_follows_model_profile():
    """인자 이름은 build_chat_kwargs가 모델 프로필을 보고 정합니다.

    구형 이름(max_tokens)으로 보내면 신형 모델이 거부합니다.
    """
    client = _client()

    assess_meeting(
        client=client,
        meeting_text=MEETING,
        model="gpt-5",
        max_retries=3,
        temperature=0.0,
        max_tokens=32768,
    )

    assert client.captured.get("max_completion_tokens") == 32768
    assert "max_tokens" not in client.captured


def test_temperature_is_omitted_for_reasoning_models():
    """temperature를 못 받는 모델에 보내면 호출 자체가 실패합니다."""
    client = _client()

    assess_meeting(
        client=client,
        meeting_text=MEETING,
        model="gpt-5",
        max_retries=3,
        temperature=0.0,
        max_tokens=32768,
    )

    assert "temperature" not in client.captured


def test_temperature_is_sent_for_chat_models():
    client = _client()

    assess_meeting(
        client=client,
        meeting_text=MEETING,
        model="gpt-4o",
        max_retries=3,
        temperature=0.0,
        max_tokens=16384,
    )

    assert client.captured.get("temperature") == 0.0


def test_empty_meeting_text_is_rejected_before_calling_llm():
    """빈 회의록은 LLM을 부르기 전에 걸러야 비용이 안 나갑니다."""
    client = _client()

    with pytest.raises(Exception):
        assess_meeting(
            client=client,
            meeting_text="   ",
            model="gpt-4o",
            max_retries=3,
            temperature=0.0,
            max_tokens=16384,
        )

    assert client.calls == []


# ── 두 단계 판정 ─────────────────────────────────────────


def test_relevant_meeting_uses_one_call_only():
    """회의 전체가 관련 내용이면 발췌를 요구하지 않습니다.

    발췌는 이 경로에서 쓰이지 않습니다. 요구하면 출력이 회의록
    길이에 비례해 커져서 긴 회의록에서 출력 상한을 넘습니다.
    """
    client = _client("relevant")

    eligibility, text = assess_meeting(
        client=client,
        meeting_text=MEETING,
        model="gpt-4o",
        max_retries=3,
        temperature=0.0,
        max_tokens=16384,
    )

    assert len(client.calls) == 1
    assert client.calls[0]["response_model"] is MeetingRelevance
    assert eligibility.status == "relevant"
    # 원문을 그대로 전달합니다.
    assert text == MEETING


def test_mixed_meeting_asks_for_paragraph_numbers():
    """mixed는 발췌 전문이 아니라 문단 번호를 받습니다.

    전문을 받으면 출력이 회의록 길이에 비례해 상한을 넘습니다.
    """
    client = _client("mixed")

    assess_meeting(
        client=client,
        meeting_text=MEETING,
        model="gpt-4o",
        max_retries=3,
        temperature=0.0,
        max_tokens=16384,
    )

    assert len(client.calls) == 2
    assert client.calls[0]["response_model"] is MeetingRelevance
    assert client.calls[1]["response_model"] is RelevantParagraphs


def test_mixed_output_does_not_grow_with_meeting_length():
    """회의록이 길어져도 2단계 요청 스키마는 그대로입니다."""
    long_meeting = "\n".join(
        f"{index}번째 줄입니다. 기능 논의를 했습니다."
        for index in range(500)
    )
    client = _client("mixed")

    assess_meeting(
        client=client,
        meeting_text=long_meeting,
        model="gpt-4o",
        max_retries=3,
        temperature=0.0,
        max_tokens=16384,
    )

    assert client.calls[1]["response_model"] is RelevantParagraphs


# ── 문단 번호 선별 ───────────────────────────────────────

NUMBERED = [(1, "가"), (2, "나"), (3, "다"), (4, "라"), (5, "마")]


def test_select_paragraphs_keeps_source_order():
    """회의 흐름이 뒤섞이면 하류가 배경과 결정의 선후를 잘못 읽습니다."""
    assert select_paragraphs(NUMBERED, [3, 1], context=0) == ["가", "다"]


def test_select_paragraphs_drops_out_of_range():
    """모델이 없는 번호를 낼 수 있으므로 코드가 거릅니다."""
    assert select_paragraphs(NUMBERED, [1, 99, -3], context=0) == ["가"]


def test_select_paragraphs_drops_duplicates():
    assert select_paragraphs(NUMBERED, [2, 2, 2], context=0) == ["나"]


def test_select_paragraphs_returns_empty_when_nothing_valid():
    assert select_paragraphs(NUMBERED, [99], context=0) == []


# ── 앞뒤 맥락 보존 ───────────────────────────────────────


def test_context_includes_neighbours():
    """대화에서는 근거와 결론이 다른 발언에 나뉘어 있습니다."""
    assert select_paragraphs(NUMBERED, [3], context=1) == [
        "나",
        "다",
        "라",
    ]


def test_context_does_not_run_past_the_edges():
    """첫 문단과 마지막 문단에서 범위를 넘지 않아야 합니다."""
    assert select_paragraphs(NUMBERED, [1], context=1) == ["가", "나"]
    assert select_paragraphs(NUMBERED, [5], context=1) == ["라", "마"]


def test_context_does_not_duplicate_overlapping_neighbours():
    """이웃한 번호를 함께 고르면 겹치는 문단이 두 번 들어가면 안 됩니다."""
    assert select_paragraphs(NUMBERED, [2, 3], context=1) == [
        "가",
        "나",
        "다",
        "라",
    ]


def test_context_is_on_by_default():
    """기본값이 0이면 실제 회의록에서 맥락이 끊깁니다."""
    assert select_paragraphs(NUMBERED, [3]) == ["나", "다", "라"]


def test_irrelevant_meeting_stops_after_first_call():
    """중단 판정에 2단계 호출을 쓰면 비용만 나갑니다."""
    client = _client("irrelevant")

    with pytest.raises(Exception):
        assess_meeting(
            client=client,
            meeting_text=MEETING,
            model="gpt-4o",
            max_retries=3,
            temperature=0.0,
            max_tokens=16384,
        )

    assert len(client.calls) == 1


def test_relevant_eligibility_allows_empty_passages():
    """relevant는 발췌를 쓰지 않으므로 비어 있어도 유효합니다."""
    MeetingEligibility(status="relevant", reason="관련 회의")


def test_mixed_eligibility_requires_passages():
    """mixed는 발췌가 곧 하류 입력이라 비면 안 됩니다."""
    with pytest.raises(Exception):
        MeetingEligibility(status="mixed", reason="일부만 관련")


def test_mixed_stops_when_no_valid_paragraph_selected():
    """고른 번호가 하나도 유효하지 않으면 진행하면 안 됩니다.

    빈 텍스트를 하류에 넘기면 노드 1이 근거 없는 기획서를 만듭니다.
    """
    client = _client("mixed", numbers=[999, -1])

    # 어떤 예외든 통과시키면 스키마 검증에 걸린 것과 구분되지 않습니다.
    # 이 경로가 스스로 걸러야 합니다.
    with pytest.raises(MeetingEligibilityError):
        assess_meeting(
            client=client,
            meeting_text=MEETING,
            model="gpt-4o",
            max_retries=3,
            temperature=0.0,
            max_tokens=16384,
        )


def test_mixed_passes_only_selected_paragraphs():
    """멀리 떨어진 문단은 하류로 가지 않아야 합니다.

    앞뒤 1개는 맥락 보존을 위해 함께 갑니다(CONTEXT_PARAGRAPHS).
    그래서 고른 문단에서 두 칸 이상 떨어진 것으로 확인합니다.
    """
    # 각 줄이 SHORT_LINE_CHARS보다 길어야 별도 문단으로 남습니다.
    meeting = (
        "데이터베이스 스키마를 어떻게 설계할지 오래 논의했고 테이블 구조를 정했습니다.\n"
        "이어서 테이블을 분리하는 기준과 공통 키를 무엇으로 둘지 자세히 정리했습니다.\n"
        "지난 주말에 다녀온 여행 이야기를 나누면서 다들 어디가 좋았는지 말했습니다.\n"
        "저녁 메뉴로 무엇을 먹을지 한참 이야기하다가 결국 근처 식당으로 정했습니다.\n"
        "마지막으로 배포 일정을 언제로 확정할지 논의하고 담당자를 나눴습니다."
    )
    client = _client("mixed", numbers=[1])

    eligibility, text = assess_meeting(
        client=client,
        meeting_text=meeting,
        model="gpt-4o",
        max_retries=3,
        temperature=0.0,
        max_tokens=16384,
    )

    assert "저녁 메뉴" not in text
    assert "배포 일정" not in text
    assert "데이터베이스 스키마를 어떻게 설계할지" in text
    assert eligibility.status == "mixed"


# ── 문단 나누기 ──────────────────────────────────────────
#
# 대화 전사본은 맞장구가 절반입니다. 줄 단위로만 쪼개면 "네.",
# "맞아요." 가 각각 문단이 되어 200개 가까운 조각이 생기고,
# 모델이 의미 있어 보이는 것만 고르면서 맥락이 끊깁니다.

LONG = "이 내용은 문단 하나로 남을 만큼 충분히 긴 발언입니다."


def test_short_lines_merge_into_previous_paragraph():
    """맞장구는 앞 발언에 속합니다."""
    text = f"{LONG}\n네.\n맞아요."
    numbered = number_paragraphs(text)

    assert len(numbered) == 1
    assert "네." in numbered[0][1]
    assert "맞아요." in numbered[0][1]


def test_long_lines_stay_separate():
    text = f"{LONG}\n{LONG}"
    assert len(number_paragraphs(text)) == 2


def test_leading_short_line_is_kept():
    """첫 줄이 짧으면 붙일 앞 문단이 없으므로 버리지 않습니다."""
    numbered = number_paragraphs(f"네.\n{LONG}")

    assert len(numbered) == 2
    assert numbered[0][1] == "네."


def test_merging_reduces_paragraph_count_on_dialogue():
    """실제 전사본 형태에서 조각 수가 실제로 줄어야 합니다."""
    dialogue = "\n".join([LONG, "네.", LONG, "맞아요.", "그렇죠.", LONG])

    numbered = number_paragraphs(dialogue)

    # 줄은 6개지만 맞장구가 앞에 붙어 3개로 줄어야 합니다.
    assert len(numbered) == 3


def test_numbering_starts_at_one():
    """프롬프트에 [1]부터 붙여 보내므로 1로 시작해야 합니다."""
    numbered = number_paragraphs(f"{LONG}\n{LONG}")
    assert [index for index, _ in numbered] == [1, 2]


def test_short_line_threshold_is_reasonable():
    """기준이 너무 크면 회의록 전체가 한 문단이 됩니다."""
    assert 10 <= SHORT_LINE_CHARS <= 60
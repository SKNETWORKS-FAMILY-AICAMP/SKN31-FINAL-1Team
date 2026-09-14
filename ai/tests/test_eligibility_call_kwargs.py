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

from meeting_analysis.eligibility import (
    MeetingEligibility,
    assess_meeting,
)


MEETING = "로그인 기능을 추가하기로 했다. 인증은 JWT를 사용한다."


class _RecordingClient:
    """create()에 들어온 인자를 기록만 하는 가짜 클라이언트."""

    def __init__(self, result):
        self._result = result
        self.captured: dict = {}
        self.chat = self  # client.chat.completions.create 형태를 흉내냅니다.
        self.completions = self

    def create(self, **kwargs):
        self.captured = kwargs
        return self._result


def _client():
    return _RecordingClient(
        MeetingEligibility(
            status="relevant",
            reason="개발 관련 회의입니다.",
            relevant_passages=[MEETING],
        )
    )


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

    assert client.captured == {}
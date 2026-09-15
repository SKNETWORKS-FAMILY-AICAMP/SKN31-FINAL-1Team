"""
tests/test_retry_config.py

shared.retry_config의 순수 함수만 — resolve_profile()은 모델명 문자열만 보고
계열 프로필을 고르는 결정적 로직이라 LLM 호출 없이 바로 검증 가능하다.

2026-09-14: structured_temperature_for() 신설 — assignee_recommend/assignment_ranking의
저난도 호출을 FAST_MODEL(retry_config.py 참고)로 옮기면서, TEMPERATURE_STRUCTURED
(DEFAULT_MODEL 기준으로 고정된 값)를 다른 계열 모델에 그대로 쓰면 안 맞을 수
있어 모델별로 다시 판단하는 함수를 추가했다. 그 판단이 맞는지만 검증한다.
"""

from shared.retry_config import (
    DEFAULT_MAX_TOKENS,
    FAST_MODEL_MAX_TOKENS,
    FAST_MODEL_PROFILE,
    _max_tokens_for,
    is_reasoning_model,
    resolve_profile,
    structured_temperature_for,
)


def test_structured_temperature_for_chat_model_is_zero():
    assert structured_temperature_for("gpt-4o") == 0.0
    assert structured_temperature_for("gpt-4o-mini") == 0.0


def test_structured_temperature_for_reasoning_model_is_none():
    assert structured_temperature_for("gpt-5") is None
    assert structured_temperature_for("gpt-5.6-sol") is None
    assert structured_temperature_for("o3") is None


def test_gpt_4o_mini_resolves_to_gpt_4o_profile():
    # FAST_MODEL 기본값(gpt-4o-mini)이 "gpt-4o 계열" 접두사에 걸려야 한다 —
    # 안 그러면 FALLBACK_PROFILE(temperature/reasoning_effort 미전송)로 빠진다.
    profile = resolve_profile("gpt-4o-mini")
    assert profile.supports_temperature is True
    assert profile.label == "gpt-4o 계열"


def test_is_reasoning_model_matches_structured_temperature():
    for model in ["gpt-4o", "gpt-4o-mini", "gpt-5", "o1", "gpt-6-astra"]:
        assert is_reasoning_model(model) == (structured_temperature_for(model) is None)


def test_fast_model_max_tokens_uses_its_own_profile_not_default_models():
    # 2026-09-15 실측 버그: OPENAI_MODEL=gpt-5(추론, 상한 32768)일 때 DEFAULT_MAX_TOKENS도
    # 32768이 되는데, FAST_MODEL(gpt-4o-mini, 실제 상한 16384) 호출에 그 값을 그대로
    # 쓰면 OpenAI가 400(max_tokens is too large)을 던졌다. FAST_MODEL_MAX_TOKENS는
    # FAST_MODEL 자신의 프로필에서 나와야 하며, OPENAI_FAST_MAX_TOKENS 환경변수를
    # 안 줬다면 FAST_MODEL_PROFILE.default_max_tokens와 같아야 한다.
    assert FAST_MODEL_MAX_TOKENS == FAST_MODEL_PROFILE.default_max_tokens
    assert FAST_MODEL_MAX_TOKENS <= 16384  # gpt-4o-mini(gpt-4o 계열)의 실제 상한


def test_fast_model_max_tokens_independent_of_default_model():
    # 이 테스트를 실행하는 .env 설정과 무관하게(현재 OPENAI_MODEL=gpt-5라 DEFAULT_MAX_TOKENS
    # 는 32768) FAST_MODEL_MAX_TOKENS는 DEFAULT_MODEL의 프로필을 빌려오면 안 된다.
    if DEFAULT_MAX_TOKENS != FAST_MODEL_PROFILE.default_max_tokens:
        assert FAST_MODEL_MAX_TOKENS != DEFAULT_MAX_TOKENS


def test_max_tokens_for_clamps_manual_override_above_model_ceiling(monkeypatch):
    # 2026-09-15: 기본값 상속이 아니라 사람이 OPENAI_FAST_MAX_TOKENS 같은 오버라이드를
    # 그 모델이 못 받는 크기로 직접 적어도(예: gpt-4o-mini에 32768) 그대로 통과시키면
    # 안 된다 — DEFAULT_MAX_TOKENS를 빌려 쓰다 걸렸던 400과 같은 부류의 실패를
    # 오버라이드 경로로도 다시 낼 수 있었다.
    monkeypatch.setenv("SOME_OVERRIDE_ENV", "32768")
    result = _max_tokens_for(FAST_MODEL_PROFILE, "SOME_OVERRIDE_ENV")  # gpt-4o-mini 계열, 실제 상한 16384
    assert result == 16384


def test_max_tokens_for_keeps_override_within_ceiling(monkeypatch):
    monkeypatch.setenv("SOME_SMALL_OVERRIDE_ENV", "1000")
    result = _max_tokens_for(FAST_MODEL_PROFILE, "SOME_SMALL_OVERRIDE_ENV")
    assert result == 1000  # 상한 이하면 사람이 적은 값을 그대로 존중

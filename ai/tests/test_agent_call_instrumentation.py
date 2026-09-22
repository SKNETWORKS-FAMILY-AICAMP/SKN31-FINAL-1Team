"""plan_draft.agent._call()의 LLM 호출 계측. 실제 API 호출 없이 가짜
클라이언트로 성공/실패 경로를 모두 검증합니다.

이 테스트는 품질·프롬프트·재시도 설정에는 관여하지 않습니다 — 계측이
성공/실패 판정이나 예외 종류·메시지를 바꾸지 않는다는 것과, usage가
없어도 죽지 않는다는 것, 회의록 원문/시스템 프롬프트가 계측 로그에
등장하지 않는다는 것만 확인합니다.
"""
from __future__ import annotations

import httpx
import pytest
from openai import APIError
from pydantic import BaseModel

from plan_draft import agent
from shared import llm_instrumentation
from shared.errors import NodeGenerationError

try:
    from instructor.core import InstructorRetryException
except ImportError:  # 구버전 instructor 호환
    from instructor.exceptions import InstructorRetryException


SECRET_API_KEY = "sk-super-secret-should-never-be-logged"
SOURCE_TEXT_MARKER = "회의록 원문 절대 로그에 나오면 안 됨"


class _FakeResult(BaseModel):
    value: str = "ok"


class _Usage:
    """openai.types.CompletionUsage를 흉내내는 최소 더미."""

    def __init__(self, prompt_tokens: int, completion_tokens: int, total_tokens: int):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


class _FakeRawResponse:
    def __init__(self, usage):
        self.usage = usage
        self.model = "fake-model"


@pytest.fixture(autouse=True)
def _clear_instrumentation():
    llm_instrumentation.clear_records()
    yield
    llm_instrumentation.clear_records()


def _make_success_client(attempts: int = 2, usage: _Usage | None = None):
    """create()가 hooks를 attempts번 울리고 계측 필드가 붙은 결과를 돌려주는
    가짜 instructor 클라이언트. 실제 OpenAI/instructor 통신은 전혀 없습니다.
    """
    calls: list[dict] = []

    class _Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            hooks = kwargs.get("hooks")
            if hooks is not None:
                for _ in range(attempts):
                    hooks.emit_completion_arguments(**kwargs)
            result = _FakeResult()
            object.__setattr__(result, "_raw_response", _FakeRawResponse(usage))
            if usage is not None:
                object.__setattr__(result, "_total_usage", usage)
            return result

    class _Chat:
        completions = _Completions()

    class _FakeClient:
        chat = _Chat()

    return _FakeClient(), calls


def test_call_records_success_metrics_with_tokens_and_attempts(monkeypatch):
    usage = _Usage(prompt_tokens=120, completion_tokens=45, total_tokens=165)
    fake_client, calls = _make_success_client(attempts=3, usage=usage)
    monkeypatch.setattr(agent, "get_client", lambda model: fake_client)

    result = agent._call(
        "system prompt", [{"role": "user", "content": SOURCE_TEXT_MARKER}],
        _FakeResult, context="run whole-plan proposal_id=P-1",
    )

    assert result.value == "ok"
    records = llm_instrumentation.get_records()
    assert len(records) == 1
    metric = records[0]
    assert metric.context == "run whole-plan proposal_id=P-1"
    assert metric.success is True
    assert metric.attempt_count == 3
    assert metric.input_tokens == 120
    assert metric.output_tokens == 45
    assert metric.total_tokens == 165
    assert metric.duration_seconds >= 0
    assert metric.error_type is None
    # hooks를 실제로 넘겼는지도 확인 — 재시도 설정 자체는 손대지 않았어야 함
    assert "hooks" in calls[0]
    assert calls[0]["max_retries"] == agent.MAX_RETRIES
    assert calls[0]["model"] == agent.MODEL


def test_call_survives_missing_usage(monkeypatch):
    """usage가 전혀 없어도(구버전/일부 provider) 생성 자체는 실패하지 않는다."""
    fake_client, _ = _make_success_client(attempts=1, usage=None)
    monkeypatch.setattr(agent, "get_client", lambda model: fake_client)

    result = agent._call("system", [], _FakeResult, context="ctx")

    assert result.value == "ok"
    metric = llm_instrumentation.get_records()[0]
    assert metric.success is True
    assert metric.input_tokens is None
    assert metric.output_tokens is None
    assert metric.total_tokens is None


def test_call_records_failure_on_retry_exhausted(monkeypatch):
    usage = _Usage(prompt_tokens=90, completion_tokens=30, total_tokens=120)

    def _raise(**kwargs):
        hooks = kwargs.get("hooks")
        if hooks is not None:
            for _ in range(4):
                hooks.emit_completion_arguments(**kwargs)
        raise InstructorRetryException(
            "재시도 소진", n_attempts=4, total_usage=usage,
        )

    class _Completions:
        create = staticmethod(_raise)

    class _Chat:
        completions = _Completions()

    class _FakeClient:
        chat = _Chat()

    monkeypatch.setattr(agent, "get_client", lambda model: _FakeClient())

    with pytest.raises(NodeGenerationError) as excinfo:
        agent._call("system", [], _FakeResult, context="run proposal_id=P-2")

    assert excinfo.value.cause_code == "LLM_RETRY_EXHAUSTED"
    metric = llm_instrumentation.get_records()[0]
    assert metric.success is False
    assert metric.error_type == "InstructorRetryException"
    assert metric.attempt_count == 4
    assert metric.context == "run proposal_id=P-2"
    assert metric.input_tokens == 90
    assert metric.output_tokens == 30
    assert metric.total_tokens == 120


def test_call_records_failure_on_config_error(monkeypatch):
    def _raise_runtime(model):
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")

    monkeypatch.setattr(agent, "get_client", _raise_runtime)

    with pytest.raises(NodeGenerationError) as excinfo:
        agent._call("system", [], _FakeResult, context="ctx")

    assert excinfo.value.cause_code == "CONFIG_ERROR"
    metric = llm_instrumentation.get_records()[0]
    assert metric.success is False
    assert metric.error_type == "RuntimeError"


def test_call_records_failure_on_api_error(monkeypatch):
    request = httpx.Request("POST", "https://api.openai.test/v1/chat/completions")

    def _raise_api_error(**kwargs):
        raise APIError("boom", request=request, body=None)

    class _Completions:
        create = staticmethod(_raise_api_error)

    class _Chat:
        completions = _Completions()

    class _FakeClient:
        chat = _Chat()

    monkeypatch.setattr(agent, "get_client", lambda model: _FakeClient())

    with pytest.raises(NodeGenerationError) as excinfo:
        agent._call("system", [], _FakeResult, context="ctx")

    assert excinfo.value.cause_code == "LLM_API_ERROR"
    metric = llm_instrumentation.get_records()[0]
    assert metric.success is False
    assert metric.error_type == "APIError"


def test_call_records_failure_on_unknown_error(monkeypatch):
    def _raise_value_error(**kwargs):
        raise ValueError("무언가 예상 못 한 오류")

    class _Completions:
        create = staticmethod(_raise_value_error)

    class _Chat:
        completions = _Completions()

    class _FakeClient:
        chat = _Chat()

    monkeypatch.setattr(agent, "get_client", lambda model: _FakeClient())

    with pytest.raises(NodeGenerationError) as excinfo:
        agent._call("system", [], _FakeResult, context="ctx")

    assert excinfo.value.cause_code == "UNKNOWN"
    metric = llm_instrumentation.get_records()[0]
    assert metric.success is False
    assert metric.error_type == "ValueError"


def test_call_log_line_never_contains_source_text_or_api_key(monkeypatch, caplog):
    usage = _Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    fake_client, _ = _make_success_client(attempts=1, usage=usage)
    monkeypatch.setattr(agent, "get_client", lambda model: fake_client)

    with caplog.at_level("INFO", logger="llm_instrumentation"):
        agent._call(
            "이것은 절대 로그에 나오면 안 되는 시스템 프롬프트",
            [{"role": "user", "content": SOURCE_TEXT_MARKER}],
            _FakeResult,
            context="run whole-plan proposal_id=P-3",
        )

    joined_logs = "\n".join(record.getMessage() for record in caplog.records)
    assert SOURCE_TEXT_MARKER not in joined_logs
    assert SECRET_API_KEY not in joined_logs
    assert "run whole-plan proposal_id=P-3" in joined_logs

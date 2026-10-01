"""shared.llm_instrumentation 단위 테스트. 실제 API 호출 없음."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from types import SimpleNamespace

from shared import llm_instrumentation


def test_safe_extract_usage_reads_total_usage_first():
    usage = SimpleNamespace(prompt_tokens=100, completion_tokens=20, total_tokens=120)
    result = SimpleNamespace(_total_usage=usage, _raw_response=None)

    input_tokens, output_tokens, total_tokens = llm_instrumentation.safe_extract_usage(result)

    assert (input_tokens, output_tokens, total_tokens) == (100, 20, 120)


def test_safe_extract_usage_falls_back_to_raw_response():
    usage = SimpleNamespace(prompt_tokens=7, completion_tokens=3, total_tokens=10)
    raw = SimpleNamespace(usage=usage)
    result = SimpleNamespace(_raw_response=raw)

    input_tokens, output_tokens, total_tokens = llm_instrumentation.safe_extract_usage(result)

    assert (input_tokens, output_tokens, total_tokens) == (7, 3, 10)


def test_safe_extract_usage_reads_retry_exception_total_usage():
    usage = SimpleNamespace(prompt_tokens=30, completion_tokens=6, total_tokens=36)
    result = SimpleNamespace(total_usage=usage)

    assert llm_instrumentation.safe_extract_usage(result) == (30, 6, 36)


def test_safe_extract_usage_derives_total_when_missing():
    usage = SimpleNamespace(prompt_tokens=7, completion_tokens=3, total_tokens=None)
    result = SimpleNamespace(_total_usage=usage)

    _, _, total_tokens = llm_instrumentation.safe_extract_usage(result)

    assert total_tokens == 10


def test_safe_extract_usage_handles_alternate_field_names():
    usage = SimpleNamespace(input_tokens=50, output_tokens=15, total_tokens=None)
    result = SimpleNamespace(_total_usage=usage)

    input_tokens, output_tokens, total_tokens = llm_instrumentation.safe_extract_usage(result)

    assert (input_tokens, output_tokens, total_tokens) == (50, 15, 65)


def test_safe_extract_usage_returns_none_triplet_when_nothing_available():
    result = SimpleNamespace()

    assert llm_instrumentation.safe_extract_usage(result) == (None, None, None)


def test_safe_extract_usage_never_raises_on_malformed_usage():
    """usage 필드가 있어도 타입이 이상하면 예외 없이 None으로 떨어져야 한다."""
    weird_usage = object()
    result = SimpleNamespace(_total_usage=weird_usage)

    assert llm_instrumentation.safe_extract_usage(result) == (None, None, None)


def test_safe_extract_usage_ignores_non_numeric_and_bool_fields():
    usage = SimpleNamespace(prompt_tokens=True, completion_tokens="20", total_tokens=None)
    result = SimpleNamespace(_total_usage=usage)

    # bool은 Real의 서브클래스이지만 토큰 수로 의미가 없으므로 제외돼야 한다.
    assert llm_instrumentation.safe_extract_usage(result) == (None, None, None)


def test_attempt_counter_counts_calls():
    counter = llm_instrumentation.AttemptCounter()
    assert counter.count == 0

    counter()
    counter(model="x")
    counter()

    assert counter.count == 3


def test_make_call_hooks_returns_working_pair():
    hooks, counter = llm_instrumentation.make_call_hooks()

    assert counter.count == 0
    if hooks is not None:  # instructor에 Hooks가 있는 버전
        hooks.emit_completion_arguments()
        hooks.emit_completion_arguments()
        assert counter.count == 2


def test_build_metrics_computes_duration_and_success_result():
    started_at = datetime.now(timezone.utc)
    start_perf = time.perf_counter()
    usage = SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3)
    result = SimpleNamespace(_total_usage=usage)

    metrics = llm_instrumentation.build_metrics(
        context="ctx", model="gpt-test", started_at=started_at,
        start_perf=start_perf, attempt_count=2, success=True, result=result,
    )

    assert metrics.context == "ctx"
    assert metrics.model == "gpt-test"
    assert metrics.success is True
    assert metrics.attempt_count == 2
    assert metrics.input_tokens == 1
    assert metrics.output_tokens == 2
    assert metrics.total_tokens == 3
    assert metrics.duration_seconds >= 0
    assert metrics.ended_at >= metrics.started_at


def test_build_metrics_failure_has_no_tokens_without_result():
    metrics = llm_instrumentation.build_metrics(
        context="ctx", model="gpt-test", started_at=datetime.now(timezone.utc),
        start_perf=time.perf_counter(), attempt_count=None, success=False,
        error_type="RuntimeError",
    )

    assert metrics.success is False
    assert metrics.error_type == "RuntimeError"
    assert metrics.input_tokens is None
    assert metrics.output_tokens is None
    assert metrics.total_tokens is None


def test_record_and_get_and_clear_records_roundtrip():
    llm_instrumentation.clear_records()
    assert llm_instrumentation.get_records() == []

    metrics = llm_instrumentation.build_metrics(
        context="ctx", model="gpt-test", started_at=datetime.now(timezone.utc),
        start_perf=time.perf_counter(), attempt_count=1, success=True,
    )
    llm_instrumentation.record_call(metrics)

    records = llm_instrumentation.get_records()
    assert records == [metrics]

    llm_instrumentation.clear_records()
    assert llm_instrumentation.get_records() == []


def test_records_are_bounded_for_long_running_process():
    llm_instrumentation.clear_records()
    for index in range(llm_instrumentation.MAX_IN_MEMORY_RECORDS + 1):
        metrics = llm_instrumentation.build_metrics(
            context=f"ctx-{index}", model="gpt-test",
            started_at=datetime.now(timezone.utc), start_perf=time.perf_counter(),
            attempt_count=1, success=True,
        )
        llm_instrumentation.record_call(metrics)

    records = llm_instrumentation.get_records()
    assert len(records) == llm_instrumentation.MAX_IN_MEMORY_RECORDS
    assert records[0].context == "ctx-1"


def test_record_call_log_message_has_no_secrets(caplog):
    llm_instrumentation.clear_records()
    metrics = llm_instrumentation.build_metrics(
        context="run whole-plan proposal_id=P-9", model="gpt-test",
        started_at=datetime.now(timezone.utc), start_perf=time.perf_counter(),
        attempt_count=1, success=True,
    )

    with caplog.at_level("INFO", logger="llm_instrumentation"):
        llm_instrumentation.record_call(metrics)

    message = caplog.records[-1].getMessage()
    assert "run whole-plan proposal_id=P-9" in message
    assert "sk-" not in message
    assert "OPENAI_API_KEY" not in message

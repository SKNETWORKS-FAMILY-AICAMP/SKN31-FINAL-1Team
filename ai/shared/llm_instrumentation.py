"""
shared/llm_instrumentation.py

LLM 호출 계측 — 기획서 생성 품질이나 프롬프트에는 관여하지 않고, 호출
하나(_call() 한 번)가 실제로 어떻게 실행됐는지만 관찰해서 기록한다.

기록 대상: 호출 맥락(context), 모델명, 시작/종료 시각, 소요시간, 실제 API
시도 횟수, 입력/출력/총 토큰, 성공 여부, (실패 시) 오류 종류.

절대 기록하지 않는 것: API 키, system/messages(회의록 원문·프롬프트 본문
전체). 호출부(agent.py)가 넘기는 context는 이미 "run whole-plan
proposal_id=..." 처럼 원문을 담지 않는 짧은 설명이므로 그대로 로그에
남겨도 된다 — 이 모듈은 그 계약을 강제하지 않고 신뢰한다(호출부 책임).

usage 읽기가 실패해도(필드 이름이 바뀌었거나, provider가 usage를 주지
않거나) 생성 자체는 절대 막지 않는다 — 모든 읽기는 getattr 기반으로
방어적으로 처리하고, 실패하면 None으로 떨어진다.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any

logger = logging.getLogger("llm_instrumentation")

try:  # instructor 1.x(v2 코어) 경로
    from instructor.core import Hooks
except ImportError:  # pragma: no cover - 구버전/향후 버전 호환
    try:
        from instructor.v2.core.hooks import Hooks
    except ImportError:  # pragma: no cover - hooks 자체가 없는 환경
        Hooks = None  # type: ignore[assignment, misc]


@dataclass(frozen=True)
class LLMCallMetrics:
    """_call() 한 번의 실행 계측 결과."""

    context: str
    model: str
    started_at: datetime
    ended_at: datetime
    duration_seconds: float
    attempt_count: int | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    success: bool
    error_type: str | None = None


_lock = Lock()
# 서비스 프로세스가 오래 살아 있어도 진단 기록 때문에 메모리가 계속
# 증가하지 않도록 최근 호출만 보관한다. 전체 이력은 INFO 로그에서 수집한다.
MAX_IN_MEMORY_RECORDS = 1_000
_records: deque[LLMCallMetrics] = deque(maxlen=MAX_IN_MEMORY_RECORDS)


class AttemptCounter:
    """instructor의 completion:kwargs 훅을 세어 실제 API 시도 횟수를 잰다.

    completion:kwargs는 재시도 루프가 실제로 API를 호출하기 직전마다 한
    번씩 발생한다(성공한 시도든 스키마 검증에 실패해 재시도로 이어진
    시도든 모두 포함). 그래서 이 값이 "실제 API 시도 횟수"의 근거가 된다
    — instructor가 예외에 담아주는 n_attempts와 같은 값이어야 하지만,
    성공 시에는 n_attempts가 노출되지 않으므로 성공/실패 모두에서 같은
    방법으로 셀 수 있게 직접 센다.
    """

    def __init__(self) -> None:
        self.count = 0

    def __call__(self, *_args: Any, **_kwargs: Any) -> None:
        self.count += 1


def make_call_hooks() -> tuple[Any | None, AttemptCounter]:
    """호출 하나 전용 Hooks 인스턴스와 시도 횟수 카운터를 만든다.

    instructor에 Hooks가 없는 버전이면(수입 실패) hooks는 None을 반환한다
    — 호출부는 이 경우 kwargs에 hooks를 아예 넣지 않으면 되고, 시도
    횟수는 이후 알 수 있는 값(예: 예외의 n_attempts)으로 대체하면 된다.
    """
    counter = AttemptCounter()
    if Hooks is None:  # pragma: no cover - 방어적 분기
        return None, counter
    hooks = Hooks()
    hooks.on("completion:kwargs", counter)
    return hooks, counter


def safe_extract_usage(result: Any) -> tuple[int | None, int | None, int | None]:
    """instructor 응답 객체에서 (입력, 출력, 총) 토큰 수를 안전하게 읽는다.

    instructor는 성공 시 결과 객체에 `_total_usage`(재시도 누적 usage)와
    `_raw_response`(마지막 시도의 원본 응답, .usage 포함)를 덧붙인다.
    버전 차이나 usage를 안 주는 상황을 대비해 어떤 조합이 와도 예외 없이
    (None, None, None)까지 떨어지게 한다 — usage가 없어도 생성 결과를
    막지 않는다는 요구사항을 계측 쪽에서 보장한다.
    """
    try:
        usage = getattr(result, "_total_usage", None)
        if usage is None:
            # InstructorRetryException은 성공 결과와 달리 누적 usage를
            # total_usage 속성에 보관한다.
            usage = getattr(result, "total_usage", None)
        if usage is None:
            raw = getattr(result, "_raw_response", None)
            usage = getattr(raw, "usage", None)
        if usage is None:
            return None, None, None

        def _first_numeric(*names: str) -> int | None:
            for name in names:
                value = getattr(usage, name, None)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    return int(value)
            return None

        input_tokens = _first_numeric("prompt_tokens", "input_tokens")
        output_tokens = _first_numeric("completion_tokens", "output_tokens")
        total_tokens = _first_numeric("total_tokens")
        if total_tokens is None and (input_tokens is not None or output_tokens is not None):
            total_tokens = (input_tokens or 0) + (output_tokens or 0)
        return input_tokens, output_tokens, total_tokens
    except Exception:  # pragma: no cover - 계측은 생성을 막지 않는다
        logger.debug("llm 호출 usage 파싱 실패 — 토큰 수치 없이 계속 진행", exc_info=True)
        return None, None, None


def build_metrics(
    *,
    context: str,
    model: str,
    started_at: datetime,
    start_perf: float,
    attempt_count: int | None,
    success: bool,
    result: Any = None,
    error_type: str | None = None,
) -> LLMCallMetrics:
    ended_at = datetime.now(timezone.utc)
    duration_seconds = max(time.perf_counter() - start_perf, 0.0)
    input_tokens = output_tokens = total_tokens = None
    if result is not None:
        input_tokens, output_tokens, total_tokens = safe_extract_usage(result)
    return LLMCallMetrics(
        context=context,
        model=model,
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=duration_seconds,
        attempt_count=attempt_count,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        success=success,
        error_type=error_type,
    )


def record_call(metrics: LLMCallMetrics) -> None:
    """계측 결과를 메모리에 쌓고(테스트/조회용) 한 줄 로그로 남긴다.

    context는 호출부 계약상 회의록 원문·API 키를 담지 않는 짧은 설명이다
    (agent.py 참고). 이 함수는 그 값을 신뢰하고 그대로 로그에 쓴다 — 여기
    말고는 어떤 필드도 자유 텍스트를 로그에 내보내지 않는다.
    """
    with _lock:
        _records.append(metrics)
    logger.info(
        "llm_call context=%s model=%s duration_seconds=%.3f attempt_count=%s "
        "input_tokens=%s output_tokens=%s total_tokens=%s success=%s%s",
        metrics.context,
        metrics.model,
        metrics.duration_seconds,
        metrics.attempt_count,
        metrics.input_tokens,
        metrics.output_tokens,
        metrics.total_tokens,
        metrics.success,
        f" error_type={metrics.error_type}" if metrics.error_type else "",
    )


def get_records() -> list[LLMCallMetrics]:
    """테스트/디버깅용 — 지금까지 쌓인 계측 기록의 복사본."""
    with _lock:
        return list(_records)


def clear_records() -> None:
    """테스트용 — 계측 기록을 비운다."""
    with _lock:
        _records.clear()

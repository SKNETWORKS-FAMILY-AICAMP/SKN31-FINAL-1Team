"""
shared/llm_client.py

모든 에이전트가 공통으로 쓰는 LLM 클라이언트 생성 로직.
각 에이전트의 schemas.py/prompt_builder.py는 그대로 재사용할 수 있다.

Provider는 OpenAI 하나만 쓴다 — 이전엔 인프라성 오류(연결 실패·타임아웃·5xx·
레이트리밋) 시 Anthropic(Claude)으로 자동 전환하는 이중화를 뒀었는데, 이번
결정(2026-09-03, 2026-09-07 재확인)으로 그 폴백 경로를 뺐다. 실제로 Claude
쪽 폴백은 API 키가 없어 라이브로 검증된 적이 없었고, 이 프로젝트 규모에서
이중화까지는 필요 없다고 판단했다. (이 파일이 한때 팀원의 PROVIDER 스위치
버전과 병합 충돌로 뒤섞여 있었는데, 이 결정에 맞춰 OpenAI 단일 경로로
정리했다.)

Instructor를 쓰면 Pydantic 모델을 response_model로 넘기는 것만으로
  · JSON 파싱
  · 스키마 검증
  · 실패 시 오류 메시지를 붙여 재호출
까지 알아서 해준다.

get_client()는 meeting_analysis/plan_draft처럼 Instructor 클라이언트를 직접
받아 호출부에서 client.chat.completions.create(...)를 부르는 기존 모듈을
위해 남겨뒀다. 새 에이전트는 아래 create_structured()를 쓰는 걸 권장한다 —
model/temperature/retry 같은 반복되는 인자를 매번 안 적어도 된다.

호출 인자(temperature / max_completion_tokens / reasoning_effort)는 모델
계열마다 다르다. build_chat_kwargs()가 retry_config의 판별 결과를 보고
계열에 맞게 조립하므로, get_client()를 직접 쓰는 모듈도 이 함수를 거치면
gpt-4o ↔ gpt-5 전환이 .env의 OPENAI_MODEL 한 줄로 끝난다.
"""

import logging
import os
from typing import Type, TypeVar

import instructor
from openai import OpenAI
from pydantic import BaseModel

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv 미설치 시, 시스템 환경변수만 사용

from .retry_config import DEFAULT_MODEL, REASONING_EFFORT, resolve_profile

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def build_chat_kwargs(
    *,
    model: str,
    messages: list[dict],
    response_model: Type[T],
    max_tokens: int,
    max_retries: int,
    temperature: float | None,
) -> dict:
    """
    모델 계열 프로필(retry_config.resolve_profile)에 맞게
    client.chat.completions.create(...) 인자를 조립한다.

      · 토큰 상한은 프로필의 token_param 이름으로 넘긴다
        (신형 모델은 max_completion_tokens, 구형 인자 max_tokens는 거부).
      · 프로필이 temperature를 받을 때만 temperature를 넣는다(None이면 생략).
      · 프로필이 reasoning_effort를 받고 값이 설정돼 있을 때만 넣는다.

    새 모델은 retry_config.MODEL_PROFILES에 한 줄 추가하면 여기로 자동 반영된다.
    """
    profile = resolve_profile(model)
    kwargs: dict = dict(
        model=model,
        messages=messages,
        response_model=response_model,
        max_retries=max_retries,
    )
    kwargs[profile.token_param] = max_tokens
    if profile.supports_temperature and temperature is not None:
        kwargs["temperature"] = temperature
    if profile.supports_reasoning_effort and REASONING_EFFORT:
        kwargs["reasoning_effort"] = REASONING_EFFORT
    return kwargs


def get_raw_client() -> OpenAI:
    """Instructor 래핑 없는 순수 OpenAI 클라이언트. 헬스체크 등 비구조화 호출용."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY가 설정되지 않았습니다. "
            "프로젝트 루트에 .env 파일을 만들거나 환경변수로 설정하세요."
        )
    return OpenAI(api_key=api_key)


_INSTRUCTOR_MODES = {
    "tools": instructor.Mode.TOOLS,
    "json": instructor.Mode.JSON,
}


def get_client(model: str = DEFAULT_MODEL) -> instructor.Instructor:
    """Instructor로 감싼 OpenAI 클라이언트. 스키마 강제 파싱 + 자동 재시도를 담당.

    구조화 출력 방식(function tools / JSON)은 모델 프로필에 따라 정해진다 —
    gpt-6-astra는 chat completions에서 function tools를 못 써서 JSON 모드로 돈다.
    """
    mode = _INSTRUCTOR_MODES.get(resolve_profile(model).instructor_mode, instructor.Mode.TOOLS)
    return instructor.from_openai(get_raw_client(), mode=mode)


def create_structured(
    *,
    system_prompt: str,
    user_message: str,
    response_model: Type[T],
    max_tokens: int,
    temperature: float | None,
    max_retries: int,
    openai_model: str = DEFAULT_MODEL,
) -> T:
    """
    OpenAI 하나로만 구조화 생성한다. 실패해도 다른 provider로 넘기지 않고
    예외를 그대로 위로 던진다 — 호출부(각 agent.py)가 이미 이 예외를 잡아서
    {"error": ...} 형태로 정리하고 있으므로 그대로 둔다.

    temperature=None이면(추론 모델) 호출 인자에서 자동으로 빠진다.
    """
    client = get_client(openai_model)
    return client.chat.completions.create(
        **build_chat_kwargs(
            model=openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_model=response_model,
            max_tokens=max_tokens,
            max_retries=max_retries,
            temperature=temperature,
        )
    )

"""
shared/llm_client.py

모든 에이전트가 공통으로 쓰는 LLM 클라이언트 생성 로직.

각 에이전트의 schemas.py/prompt_builder.py는 그대로 재사용할 수 있다.

Provider 폴백 — OpenAI가 인프라성 오류(연결 실패, 타임아웃, 5xx, 레이트리밋)로
실패하면 Anthropic(Claude)으로 자동 전환한다. 요청 자체가 잘못된 경우(4xx)는
어느 provider로 보내도 똑같이 실패하므로 폴백하지 않고 바로 올린다.
"""

import logging
import os
from typing import Type, TypeVar

import anthropic
import instructor
import openai
from openai import OpenAI
from pydantic import BaseModel

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv 미설치 시, 시스템 환경변수만 사용

from .retry_config import DEFAULT_MODEL, FALLBACK_MODEL

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# OpenAI 호출이 이 예외들로 실패했을 때만 Claude로 폴백한다 — 인프라성 오류로
# 한정한다. 400(BadRequestError) 같은 요청 자체 오류는 폴백해도 똑같이
# 실패하므로 제외한다.
_FALLBACK_TRIGGERS = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.InternalServerError,  # 5xx
)


def get_client() -> instructor.Instructor:
    """Instructor로 감싼 OpenAI 클라이언트. 스키마 강제 파싱 + 자동 재시도를 담당."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY가 설정되지 않았습니다. "
            "프로젝트 루트에 .env 파일을 만들거나 환경변수로 설정하세요."
        )
    return instructor.from_openai(OpenAI(api_key=api_key))


def get_anthropic_client() -> instructor.Instructor:
    """Instructor로 감싼 Anthropic 클라이언트. OpenAI 인프라 장애 시 폴백용."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY가 설정되지 않았습니다. "
            "OpenAI 장애 시 폴백을 쓰려면 .env에 추가하세요."
        )
    return instructor.from_anthropic(anthropic.Anthropic(api_key=api_key))


def create_structured(
    *,
    system_prompt: str,
    user_message: str,
    response_model: Type[T],
    max_tokens: int,
    temperature: float,
    max_retries: int,
    openai_model: str = DEFAULT_MODEL,
    fallback_model: str = FALLBACK_MODEL,
) -> T:
    """
    OpenAI로 먼저 시도하고, 인프라성 오류일 때만 Anthropic(Claude)으로 폴백한다.
    두 provider는 호출 파라미터 형태가 달라(OpenAI는 system을 messages 안에,
    Anthropic은 system을 별도 인자로 받음 / max_tokens 파라미터명도 다름) 이 함수가
    그 차이를 흡수한다 — 호출부(agent.py)는 provider 차이를 몰라도 된다.
    """
    try:
        client = get_client()
        return client.chat.completions.create(
            model=openai_model,
            max_completion_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_model=response_model,
            max_retries=max_retries,
        )
    except _FALLBACK_TRIGGERS as e:
        logger.warning(
            "OpenAI 호출이 인프라성 오류로 실패해 Claude(%s)로 폴백합니다: %s",
            fallback_model, e,
        )
        anthropic_client = get_anthropic_client()
        return anthropic_client.messages.create(
            model=fallback_model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            response_model=response_model,
            max_retries=max_retries,
        )

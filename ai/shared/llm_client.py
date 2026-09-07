"""
Instructor 클라이언트 생성.

모든 에이전트가 공통으로 쓰는 LLM 클라이언트 생성 로직.

각 에이전트의 schemas.py/prompt_builder.py는 그대로 재사용할 수 있다.

Provider는 OpenAI 하나만 쓴다 — 이전엔 인프라성 오류(연결 실패·타임아웃·5xx·
레이트리밋) 시 Anthropic(Claude)으로 자동 전환하는 이중화를 뒀었는데, 이번
결정(2026-09-03)으로 그 폴백 경로를 뺐다. 실제로 Claude 쪽 폴백은 API 키가
없어 라이브로 검증된 적이 없었고, 이 프로젝트 규모에서 이중화까지는 필요
없다고 판단했다.
Instructor를 쓰면 Pydantic 모델을 response_model로 넘기는 것만으로
  · JSON 파싱
  · 스키마 검증
  · 실패 시 오류 메시지를 붙여 재호출
까지 알아서 해줍니다.

즉 설계 문서의 "[1] 스키마 검증 + 1회 재호출" 단계가
이 클라이언트로 대체됩니다. 손으로 짤 필요가 없습니다.

evidence 검증과 교차 규칙 검증은 Instructor가 해주지 않으므로
각 노드에서 따로 수행합니다.

※ 여나가 제안 형태로 먼저 채웠습니다.
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

from .retry_config import DEFAULT_MODEL

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

from .retry_config import PROVIDER


def get_client():
    """provider에 맞는 Instructor 클라이언트를 반환합니다."""
    if PROVIDER == "anthropic":
        from anthropic import Anthropic

        return instructor.from_anthropic(
            Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        )

    if PROVIDER == "openai":
        from openai import OpenAI

        return instructor.from_openai(
            OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
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


def create_structured(
    *,
    system_prompt: str,
    user_message: str,
    response_model: Type[T],
    max_tokens: int,
    temperature: float,
    max_retries: int,
    openai_model: str = DEFAULT_MODEL,
) -> T:
    """
    OpenAI 하나로만 구조화 생성한다. 실패해도 다른 provider로 넘기지 않고
    예외를 그대로 위로 던진다 — 호출부(각 agent.py)가 이미 이 예외를 잡아서
    {"error": ...} 형태로 정리하고 있으므로 그대로 둔다.
    """
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
    raise ValueError(f"알 수 없는 provider: {PROVIDER}")

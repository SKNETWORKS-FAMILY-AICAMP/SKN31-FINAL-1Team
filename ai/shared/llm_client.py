"""
Instructor 클라이언트 생성.

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

import os

import instructor

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

    raise ValueError(f"알 수 없는 provider: {PROVIDER}")

"""
shared/llm_client.py

모든 에이전트가 공통으로 쓰는 LLM 클라이언트 생성 로직.
클라이언트 생성 방식(Instructor 래핑, API 키 로드)을 한 곳에 모아두면,
나중에 모델을 바꾸거나 재시도 정책을 바꿀 때 에이전트 폴더 7개를
전부 고칠 필요 없이 이 파일 하나만 수정하면 된다.
"""

import os

import instructor
from anthropic import Anthropic


def get_client() -> instructor.Instructor:
    """Instructor로 감싼 Anthropic 클라이언트. 스키마 강제 파싱 + 자동 재시도를 담당."""
    return instructor.from_anthropic(
        Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    )

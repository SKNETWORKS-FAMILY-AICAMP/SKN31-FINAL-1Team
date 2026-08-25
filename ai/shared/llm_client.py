"""
shared/llm_client.py

모든 에이전트가 공통으로 쓰는 LLM 클라이언트 생성 로직.

각 에이전트의 schemas.py/prompt_builder.py는 그대로 재사용할 수 있다
"""

import os

import instructor
from openai import OpenAI

try:
    from dotenv import load_dotenv
    load_dotenv()  
except ImportError:
    pass  # python-dotenv 미설치 시, 시스템 환경변수만 사용


def get_client() -> instructor.Instructor:
    """Instructor로 감싼 OpenAI 클라이언트. 스키마 강제 파싱 + 자동 재시도를 담당."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY가 설정되지 않았습니다. "
            "프로젝트 루트에 .env 파일을 만들거나 환경변수로 설정하세요."
        )
    return instructor.from_openai(OpenAI(api_key=api_key))

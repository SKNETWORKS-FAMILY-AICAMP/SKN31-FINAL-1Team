"""
모델·재시도 기본값.

노드마다 모델명과 temperature를 따로 적으면 나중에 바꿀 때 다 뒤져야 합니다.
여기 모아둡니다.


"""

import os

from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.getenv("LLM_PROVIDER", "openai")

MODEL = os.getenv("LLM_MODEL") or {
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-4o",
}[PROVIDER]

MAX_TOKENS = 8000

# 추출·구조화 작업은 0으로 둡니다.
# 프롬프트를 고쳤을 때 결과가 달라진 이유가 프롬프트 때문인지
# 샘플링 때문인지 구분하려면 다른 변수가 없어야 합니다.
TEMPERATURE = 0

# Instructor의 자동 재시도 횟수.
# 검증에 실패하면 Instructor가 오류 메시지를 붙여 알아서 다시 부릅니다.
# 2회를 넘기면 같은 실패가 반복될 가능성이 높고 비용만 듭니다.
MAX_RETRIES = 3

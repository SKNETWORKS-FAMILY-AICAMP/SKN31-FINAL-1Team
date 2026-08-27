"""
shared/retry_config.py

에이전트 전반에 적용되는 모델·재시도 기본값.
EX-LLM 계열 예외처리(타임아웃, 파싱 실패)에 대응하는 공통 상수.
개별 에이전트가 다른 값이 필요하면 자기 agent.py에서 이 기본값을 덮어쓴다.
"""

DEFAULT_MODEL = "gpt-4o"
DEFAULT_MAX_TOKENS = 8000

# 구조화 생성(JSON 출력) 노드는 0.0, 자연어 답변 생성 노드는 0.3
TEMPERATURE_STRUCTURED = 0.0
TEMPERATURE_GENERATIVE = 0.3

# 스키마 파싱 실패 시 재시도 횟수 (EX-LLM-004 대응)
MAX_RETRIES = 2

# 단일 LLM 호출 타임아웃(초) — 초과 시 EX-LLM-001로 처리
REQUEST_TIMEOUT_SECONDS = 30

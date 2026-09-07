"""
shared/retry_config.py

에이전트 전반에 적용되는 모델·재시도 기본값. 노드마다 모델명과 temperature를
따로 적으면 나중에 바꿀 때 다 뒤져야 하므로 여기 모아둔다.

Provider는 OpenAI만 쓴다 — Anthropic(Claude) 지원은 제거했다(2026-09-07,
llm_client.py 참고. 원래 이 파일엔 팀원(여나)이 추가한 PROVIDER 스위치 버전과
이 세션에서 만든 버전이 병합 충돌로 뒤섞여 있었는데, "Anthropic 제거" 결정에
맞춰 정리했다). 아래 PROVIDER/MODEL/MAX_TOKENS/TEMPERATURE는
meeting_analysis, plan_draft가 get_client()를 직접 호출하며 참조하는 이름이라
그대로 남겨뒀다 — 값은 이제 항상 OpenAI 기준으로 고정이고, 더 이상
환경변수로 anthropic으로 바뀌지 않는다.
"""

# --- task_generation / requirement_draft / assignee_mapping / assignee_recommend가
#     create_structured()를 통해 쓰는 값 ---
DEFAULT_MODEL = "gpt-4o"

# gpt-4o의 실제 최대 출력 토큰 상한 — 2026-09-03 확인.
DEFAULT_MAX_TOKENS = 16384

# 구조화 생성(JSON 출력) 노드는 0.0, 자연어 답변 생성 노드는 0.3
TEMPERATURE_STRUCTURED = 0.0
TEMPERATURE_GENERATIVE = 0.3

# 스키마 파싱 실패 시 재시도 횟수 (EX-LLM-004 대응)
MAX_RETRIES = 2

# 단일 LLM 호출 타임아웃(초) — 초과 시 EX-LLM-001로 처리
REQUEST_TIMEOUT_SECONDS = 30

# --- meeting_analysis / plan_draft가 get_client()를 직접 호출하며 쓰는 값 ---
PROVIDER = "openai"  # Anthropic 지원 제거 — 더 이상 환경변수로 바뀌지 않는다.
MODEL = DEFAULT_MODEL
MAX_TOKENS = DEFAULT_MAX_TOKENS
TEMPERATURE = TEMPERATURE_STRUCTURED

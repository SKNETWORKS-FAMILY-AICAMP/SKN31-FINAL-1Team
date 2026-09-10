"""
shared/retry_config.py

에이전트 전반에 적용되는 모델·재시도 기본값. 노드마다 모델명과 temperature를
따로 적으면 나중에 바꿀 때 다 뒤져야 하므로 여기 모아둔다.

────────────────────────────────────────────────────────────────────────
모델은 .env로 고른다. 프롬프트를 고치면서 모델별 결과를 비교하려면
OPENAI_MODEL 한 줄만 바꾸고 파이프라인을 다시 돌리면 된다.

    # ai/.env
    OPENAI_MODEL=gpt-4o            # 기본
    OPENAI_MODEL=gpt-5-mini
    OPENAI_MODEL=gpt-5.6-sol       # gpt-5 계열 변종도 접두사로 자동 인식
    OPENAI_MODEL=gpt-5.6-terra
    OPENAI_MODEL=gpt-5.6-luna
    OPENAI_MAX_TOKENS=32768        # (선택) 출력 토큰 상한 override
    OPENAI_REASONING_EFFORT=low    # (선택) 추론 계열에서만 의미. minimal|low|medium|high

모델마다 호출 규격이 다르다 — gpt-4o는 temperature를 받고 상한이 16384,
gpt-5/gpt-6/o-시리즈(추론)는 temperature를 못 받고(기본값 1 고정)
max_completion_tokens만 받으며 reasoning_effort를 추가로 받는다.
이 차이를 아래 MODEL_PROFILES 표에
계열별로 한 줄씩 적어두고, resolve_profile(model)이 모델명을 보고 해당 프로필을
고른다. llm_client.build_chat_kwargs()가 그 프로필대로 호출 인자를 조립한다.

  → 새 모델이 나오면 MODEL_PROFILES에 (접두사, 프로필) 한 줄만 추가하면
    .env의 OPENAI_MODEL 교체만으로 바로 쓸 수 있다.
────────────────────────────────────────────────────────────────────────

Provider는 OpenAI만 쓴다 — Anthropic(Claude) 지원은 제거했다(2026-09-07,
llm_client.py 참고). 아래 PROVIDER/MODEL/MAX_TOKENS/TEMPERATURE는
meeting_analysis, plan_draft가 참조하는 이름이라 그대로 남겨뒀다.
"""

import logging
import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv 미설치 시, 시스템 환경변수만 사용

logger = logging.getLogger(__name__)


def _env(name: str, default: str = "") -> str:
    """환경변수 값에서 따옴표·공백·줄 끝 주석을 떼어낸다."""
    raw = os.environ.get(name, default)
    return raw.split("#", 1)[0].strip().strip('"').strip("'")


# ── 모델 계열 프로필 ──────────────────────────────────────────────────
@dataclass(frozen=True)
class ModelProfile:
    """한 모델 계열의 호출 규격.

    label                   : 로그용 사람이 읽는 이름
    supports_temperature    : temperature 인자를 받는가 (추론 모델은 False)
    supports_reasoning_effort: reasoning_effort 인자를 받는가
    token_param             : 출력 토큰 상한을 넘길 인자 이름
    default_max_tokens      : OPENAI_MAX_TOKENS 미설정 시 기본 상한
    default_reasoning_effort: OPENAI_REASONING_EFFORT 미설정 시 기본값
    instructor_mode         : 구조화 출력 방식.
        "tools" = function calling (기본, gpt-4o·gpt-5에서 가장 안정적)
        "json"  = response_format=json_object (gpt-6-astra는 chat completions에서
                  function tools를 못 써서 이쪽만 됨)
    """
    label: str
    supports_temperature: bool
    supports_reasoning_effort: bool
    default_max_tokens: int
    token_param: str = "max_completion_tokens"
    default_reasoning_effort: str | None = None
    instructor_mode: str = "tools"


# 위에서부터 첫 번째로 접두사가 맞는 프로필을 쓴다. 순서 주의:
# 더 구체적인 접두사(gpt-5-chat, gpt-5.6)를 넓은 접두사(gpt-5)보다 먼저 둔다.
MODEL_PROFILES: list[tuple[tuple[str, ...], ModelProfile]] = [
    (
        ("gpt-4o", "gpt-4.1", "gpt-4-", "gpt-3.5"),
        ModelProfile(
            label="gpt-4o 계열",
            supports_temperature=True,
            supports_reasoning_effort=False,
            default_max_tokens=16384,
        ),
    ),
    (
        ("gpt-5-chat", "gpt-5.6-chat"),
        ModelProfile(
            label="gpt-5 chat (비추론)",
            supports_temperature=True,
            supports_reasoning_effort=False,
            default_max_tokens=16384,
        ),
    ),
    (
        # gpt-5.6-* / gpt-6-* 는 /v1/chat/completions에서 function tools를
        # reasoning_effort와 함께 못 쓴다 (400: "use /v1/responses or set
        # reasoning_effort to 'none'"). instructor를 JSON 모드로 돌리면
        # reasoning_effort까지 정상 동작한다. gpt-5(무印) / o-시리즈는 tools 그대로 OK.
        # ── 반드시 아래 ("gpt-5", ...) 항목보다 먼저 와야 gpt-5.6-*가 여기 걸린다.
        ("gpt-5.6", "gpt-6"),
        ModelProfile(
            label="추론 계열 gpt-5.6 / gpt-6 (JSON 모드)",
            supports_temperature=False,
            supports_reasoning_effort=True,
            default_max_tokens=32768,
            default_reasoning_effort="low",
            instructor_mode="json",
        ),
    ),
    (
        ("gpt-5", "o1", "o1-", "o3", "o3-", "o4", "o4-"),
        ModelProfile(
            label="추론 계열 (gpt-5 / o-시리즈)",
            supports_temperature=False,
            supports_reasoning_effort=True,
            default_max_tokens=32768,
            default_reasoning_effort="low",
        ),
    ),
]

# 어느 접두사에도 안 맞는 모델. 가장 보수적으로(temperature·reasoning_effort 없이)
# 호출한다 — 새 모델이라도 일단 돌아가고, 로그로 프로필 추가를 알린다.
FALLBACK_PROFILE = ModelProfile(
    label="미등록 모델(보수적 기본값)",
    supports_temperature=False,
    supports_reasoning_effort=False,
    default_max_tokens=16384,
)


def resolve_profile(model: str) -> ModelProfile:
    """모델명 → 계열 프로필. 못 찾으면 FALLBACK_PROFILE."""
    m = model.lower().strip()
    for prefixes, profile in MODEL_PROFILES:
        if m.startswith(prefixes):
            return profile
    return FALLBACK_PROFILE


def is_reasoning_model(model: str) -> bool:
    """하위호환용 — temperature를 못 받는 계열이면 True."""
    return not resolve_profile(model).supports_temperature


# ── .env에서 읽어 확정 ────────────────────────────────────────────────
DEFAULT_MODEL = _env("OPENAI_MODEL", "gpt-4o")
PROFILE = resolve_profile(DEFAULT_MODEL)
IS_REASONING_MODEL = not PROFILE.supports_temperature

# 출력 토큰 상한: .env가 있으면 우선, 없으면 프로필 기본값.
DEFAULT_MAX_TOKENS = int(_env("OPENAI_MAX_TOKENS", str(PROFILE.default_max_tokens)))

# temperature: 구조화 생성(JSON) 0.0 / 자연어 답변 0.3.
# 프로필이 temperature를 안 받으면 None → 호출 시 인자 자체를 생략.
TEMPERATURE_STRUCTURED = 0.0 if PROFILE.supports_temperature else None
TEMPERATURE_GENERATIVE = 0.3 if PROFILE.supports_temperature else None

# reasoning_effort: 프로필이 받을 때만. .env 우선, 없으면 프로필 기본값.
if PROFILE.supports_reasoning_effort:
    REASONING_EFFORT = _env(
        "OPENAI_REASONING_EFFORT", PROFILE.default_reasoning_effort or "low"
    )
else:
    REASONING_EFFORT = None

# 스키마 파싱 실패 시 재시도 횟수 (EX-LLM-004 대응)
MAX_RETRIES = 2

# 단일 LLM 호출 타임아웃(초) — 초과 시 EX-LLM-001로 처리
REQUEST_TIMEOUT_SECONDS = 30

# --- meeting_analysis / plan_draft가 get_client()를 직접 호출하며 쓰는 값 ---
PROVIDER = "openai"  # Anthropic 지원 제거 — 더 이상 환경변수로 바뀌지 않는다.
MODEL = DEFAULT_MODEL
MAX_TOKENS = DEFAULT_MAX_TOKENS
TEMPERATURE = TEMPERATURE_STRUCTURED

if PROFILE is FALLBACK_PROFILE:
    logger.warning(
        "OPENAI_MODEL=%r 는 MODEL_PROFILES에 등록된 계열이 없습니다 — "
        "보수적 기본값으로 호출합니다(temperature/reasoning_effort 미전송, "
        "max_tokens=%d). retry_config.MODEL_PROFILES에 항목을 추가하세요.",
        DEFAULT_MODEL, DEFAULT_MAX_TOKENS,
    )
logger.info(
    "LLM 모델=%s (%s) · max_tokens=%d · temperature=%s · reasoning_effort=%s · mode=%s",
    DEFAULT_MODEL, PROFILE.label, DEFAULT_MAX_TOKENS,
    TEMPERATURE_STRUCTURED, REASONING_EFFORT, PROFILE.instructor_mode,
)


def describe() -> str:
    """지금 어떤 모델·설정으로 도는지 사람이 읽을 형태로. (ai/show_model.py에서 사용)"""
    src_tok = "환경변수" if _env("OPENAI_MAX_TOKENS") else "프로필 기본값"
    src_eff = "환경변수" if _env("OPENAI_REASONING_EFFORT") else "프로필 기본값"
    rows = [
        ("모델 (OPENAI_MODEL)", DEFAULT_MODEL),
        ("계열 프로필", PROFILE.label),
        ("출력 토큰 상한", f"{DEFAULT_MAX_TOKENS}  ({src_tok})"),
        (
            "temperature",
            f"구조화={TEMPERATURE_STRUCTURED} / 생성={TEMPERATURE_GENERATIVE}"
            if PROFILE.supports_temperature
            else "미지원 (추론 모델 — 인자 전송 안 함)",
        ),
        (
            "reasoning_effort",
            f"{REASONING_EFFORT}  ({src_eff})"
            if PROFILE.supports_reasoning_effort
            else "미지원",
        ),
        ("구조화 출력 방식", f"{PROFILE.instructor_mode}  (tools=function calling / json=response_format)"),
        ("스키마 재시도", str(MAX_RETRIES)),
        ("요청 타임아웃(초)", str(REQUEST_TIMEOUT_SECONDS)),
    ]
    width = max(len(k) for k, _ in rows)
    lines = ["현재 AI 에이전트 LLM 설정", "─" * 44]
    lines += [f"{k.ljust(width)} : {v}" for k, v in rows]
    if PROFILE is FALLBACK_PROFILE:
        lines += ["", "⚠ 등록된 계열 프로필이 없어 보수적 기본값으로 동작합니다."]
    return "\n".join(lines)


if __name__ == "__main__":
    print(describe())

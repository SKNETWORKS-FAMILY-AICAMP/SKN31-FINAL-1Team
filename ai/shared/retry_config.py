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
# 더 구체적인 접두사(gpt-5-chat)를 넓은 접두사(gpt-5)보다 먼저 둔다.
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
        ("gpt-5", "o1", "o1-", "o3", "o3-", "o4", "o4-"),
        ModelProfile(
            label="추론 계열 (gpt-5 / gpt-5.6-* / o-시리즈)",
            supports_temperature=False,
            supports_reasoning_effort=True,
            default_max_tokens=32768,
            default_reasoning_effort="low",
        ),
    ),
    (
        # gpt-6-astra는 /v1/chat/completions에서 function tools를 못 쓴다
        # ("use /v1/responses or set reasoning_effort to 'none'") — 그래서
        # instructor를 JSON 모드로 돌린다. reasoning_effort는 JSON 모드에서는 OK.
        ("gpt-6",),
        ModelProfile(
            label="추론 계열 gpt-6 (JSON 모드)",
            supports_temperature=False,
            supports_reasoning_effort=True,
            default_max_tokens=32768,
            default_reasoning_effort="low",
            instructor_mode="json",
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


def _max_tokens_for(profile: ModelProfile, env_name: str) -> int:
    """env_name 오버라이드가 있으면 쓰되, 그 모델 계열의 실제 상한(profile.default_max_tokens)을
    넘지 못하게 자른다.

    2026-09-15: DEFAULT_MAX_TOKENS를 FAST_MODEL 호출에 그대로 재사용하다 걸린 400
    (max_tokens is too large)을 고치면서, FAST_MODEL_MAX_TOKENS를 자기 프로필
    기준으로 따로 뒀는데 — 그 값도 OPENAI_FAST_MAX_TOKENS로 사람이 직접 오버라이드할
    수 있고, 그때는 아무 검증이 없어 같은 부류의 400을 다시 낼 수 있었다(예:
    FAST_MODEL=gpt-4o-mini인데 OPENAI_FAST_MAX_TOKENS=32768로 잘못 적는 경우).
    기본값 상속이든 사람이 직접 적은 오버라이드든, 이 함수를 거치면 항상 그 모델이
    실제로 받을 수 있는 값 이하로 잘린다.
    """
    value = int(_env(env_name, str(profile.default_max_tokens)))
    return min(value, profile.default_max_tokens)


# ── .env에서 읽어 확정 ────────────────────────────────────────────────
DEFAULT_MODEL = _env("OPENAI_MODEL", "gpt-4o")
PROFILE = resolve_profile(DEFAULT_MODEL)
IS_REASONING_MODEL = not PROFILE.supports_temperature

# 출력 토큰 상한: .env가 있으면 우선, 없으면 프로필 기본값 — 어느 쪽이든 그 모델
# 계열의 실제 상한을 넘지 않게 _max_tokens_for()가 자른다.
DEFAULT_MAX_TOKENS = _max_tokens_for(PROFILE, "OPENAI_MAX_TOKENS")

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

# 2026-09-15: 노드①(회의록 구조화)은 56분짜리 긴 회의록처럼 여러 화제가 섞인
# 입력을 종합적으로 판단해 프로젝트 범위를 골라야 하는데, gpt-4o로는 이 판단이
# 매번 좁은 화제 하나로 쏠리는 현상이 실측됨(같은 입력을 여러 번 돌려도 일관되게
# 좁게 나옴 — 프롬프트/few-shot 보강으로도 해결 안 됨). 같은 입력을 추론 계열
# 모델(gpt-5)로 돌리자 훨씬 넓고 완전한 결과가 나와, 이 노드 하나만 강한 모델로
# 분리했다(meeting_analysis/node.py 참고). 속도가 훨씬 느려지는 트레이드오프가
# 있지만(실측 약 100초/건), 회의록 분석은 반복 실행되는 단계가 아니라 회의록당
# 1회만 도는 단계라 감내 가능하다고 판단.
STRONG_MODEL = _env("OPENAI_STRONG_MODEL", "gpt-5")
STRONG_MODEL_PROFILE = resolve_profile(STRONG_MODEL)
STRONG_MODEL_MAX_TOKENS = _max_tokens_for(STRONG_MODEL_PROFILE, "OPENAI_STRONG_MAX_TOKENS")

# 2026-09-14: 반대 방향 — 판단 난이도가 낮은 호출(코드가 이미 정한 결과를 한두
# 문장으로 서술만 하는 것 — 배정 근거 문장, 보류 사유 설명, 패키지 분할 여부
# 판단)엔 DEFAULT_MODEL보다 가볍고 빠른 모델을 따로 쓴다. 실제 추론이 필요한
# task_generation과 assignment_ranking.score_candidate_fit(경력기술서 내용
# 대조)는 DEFAULT_MODEL을 그대로 쓴다 — 호출부가 openai_model=FAST_MODEL을
# 명시한 곳만 이 모델을 탄다, 나머지는 그대로 DEFAULT_MODEL.
FAST_MODEL = _env("OPENAI_FAST_MODEL", "gpt-4o-mini")
FAST_MODEL_PROFILE = resolve_profile(FAST_MODEL)
# 2026-09-15: DEFAULT_MAX_TOKENS를 그대로 재사용하면 안 된다 — DEFAULT_MODEL이
# 추론 계열(예: gpt-5, 상한 32768)일 때 DEFAULT_MAX_TOKENS도 32768이 되는데,
# FAST_MODEL(gpt-4o-mini, 실제 상한 16384)에 그대로 넘기면 OpenAI가 400을
# 던진다(실측: "max_tokens is too large: 32768 ... at most 16384"). STRONG_MODEL이
# 이미 이 패턴(자기 프로필 기준 상한)을 쓰고 있어 FAST_MODEL도 동일하게 맞춘다.
FAST_MODEL_MAX_TOKENS = _max_tokens_for(FAST_MODEL_PROFILE, "OPENAI_FAST_MAX_TOKENS")


def structured_temperature_for(model: str) -> float | None:
    """model의 계열 프로필을 보고 구조화 생성용 temperature(0.0 또는 None)를 고른다.

    위 TEMPERATURE_STRUCTURED는 DEFAULT_MODEL 기준으로 한 번만 고정된 값이라,
    DEFAULT_MODEL과 다른 계열의 모델(FAST_MODEL·STRONG_MODEL)로 호출할 땐 맞지
    않을 수 있다 — build_chat_kwargs()가 모델별로 supports_temperature를 다시
    확인해 안 받는 모델엔 알아서 안 보내주긴 하지만(STRONG_MODEL 호출부가 그
    가드에 기대는 중), 반대 방향(그 모델은 받는데 TEMPERATURE_STRUCTURED가
    None이라 안 보내는 경우)까지 맞추려면 모델별로 다시 판단해야 한다.
    """
    return 0.0 if resolve_profile(model).supports_temperature else None

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
        ("강한 모델 (OPENAI_STRONG_MODEL, 회의록 분석 전용)", STRONG_MODEL + ("  (환경변수)" if _env("OPENAI_STRONG_MODEL") else "  (기본값)")),
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

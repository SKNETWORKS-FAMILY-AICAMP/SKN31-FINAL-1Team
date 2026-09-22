"""
노드①(회의록 구조화) 진입 전 관련성 판정 — mixed 필터링 실제 API 회귀 테스트.

## 왜 필요한가

2026-09-16에 실측으로 재현한 문제: eligibility.py의 mixed 2단계
(select_paragraphs)는 예전에 모델이 고른 문단의 앞뒤 1개를 코드가
무조건 끌어왔다(CONTEXT_PARAGRAPHS=1). 개발 논의 문단 바로 다음에
회식·워크샵 같은 무관한 잡담이 이어지면, 모델이 그 잡담 문단을 단
한 번도 직접 고르지 않았는데도 "이웃이라서" relevant_text에 새어
들어갔다(29,769자 실제 회의록 + 잡담 주입, 6회 반복 중 3회 재현).

고친 내용: CONTEXT_PARAGRAPHS를 0으로 낮추고, "이어지는 문맥인가"
판단을 eligibility_prompt.PARAGRAPH_SYSTEM_PROMPT의 명시적 지시로
모델에게 맡겼다(원문 대조처럼 코드가 검증할 수 있는 사실이 아니라
의미 판단이므로). 이 테스트는 그 수정이 실제로 잡담을 걸러내면서도
경계에 인접한 진짜 개발 논의 문단은 계속 포함하는지 확인한다.

## 왜 기본으로는 안 도는가

- 실제 OpenAI API를 호출한다.
- 관련성 판정 모델(MODEL, 기본 gpt-4o)은 temperature=0이어도 완전한
  결정론을 보장하지 않는다.

RUN_LIVE_API_TESTS=1 pytest tests/test_live_eligibility_mixed_regression.py -v
"""

import os
from pathlib import Path

import pytest

from meeting_analysis.eligibility import assess_meeting
from shared.llm_client import get_client
from shared.retry_config import MAX_RETRIES, MAX_TOKENS, MODEL, TEMPERATURE

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "meeting_musinsa_long.txt"

# 실제 회의록에는 없는 단어만 골라, 나오면 100% 주입한 잡담이 새어
# 들어간 것으로 판단할 수 있게 한다.
IRRELEVANT_BLOCK = """
자, 그럼 다음 주제로 넘어가기 전에 하나만 얘기하고 갈게요.
이번 주 금요일 저녁에 회식 어디서 할지 정해야 하는데, 지난번에
갔던 강남 고깃집 어떠셨어요? 거기 예약 가능한지 제가 확인해볼게요.
아니면 근처에 새로 생긴 이자카야도 괜찮다고 하던데, 다들 어디가
좋으신지 메신저로 투표 부탁드려요.
그리고 다음 주 화요일에 전체 워크샵 있는 거 아시죠? 장소는 아직
미정인데 총무팀에서 공지 나올 거예요. 이번엔 1박 2일이라서
숙소도 미리 정해야 하고, 참가 여부도 이번 주 안에 회신 주셔야
합니다. 개인 사정으로 못 오시는 분은 미리 말씀해 주세요.
아 참, 이번 달 생일자 케이크는 총무팀에서 준비한다고 하니까
따로 준비 안 하셔도 됩니다. 자, 그럼 원래 얘기로 돌아가서
계속 진행하겠습니다.
""".strip()

IRRELEVANT_MARKERS = ["회식", "워크샵", "생일자 케이크"]


def _build_mixed_text() -> str:
    original = FIXTURE_PATH.read_text(encoding="utf-8")
    mid = len(original) // 2
    split_at = original.find("\n", mid)
    if split_at == -1:
        split_at = mid
    return original[:split_at] + "\n\n" + IRRELEVANT_BLOCK + "\n\n" + original[split_at:]


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_API_TESTS") != "1",
    reason=(
        "실제 OpenAI API를 호출하는 유료·비결정 테스트입니다. "
        "RUN_LIVE_API_TESTS=1로 명시적으로 켜야 실행됩니다."
    ),
)
def test_긴_회의록에_섞인_잡담이_구조화_입력으로_새지_않는다():
    text = _build_mixed_text()
    client = get_client(MODEL)

    result, relevant_text = assess_meeting(
        client=client,
        meeting_text=text,
        glossary_text="",
        model=MODEL,
        max_retries=MAX_RETRIES,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )

    assert result.status == "mixed"

    leaked = [marker for marker in IRRELEVANT_MARKERS if marker in relevant_text]
    assert not leaked, (
        f"관련 없는 내용이 구조화 입력에 새어 들어갔습니다: {leaked}. "
        "eligibility.py CONTEXT_PARAGRAPHS·select_paragraphs 참고."
    )

    # 잡담을 거르는 김에 진짜 개발 논의까지 함께 잘려나가면 안 된다.
    assert "스타일" in relevant_text or "태그" in relevant_text
    assert "리셀" in relevant_text or "크림" in relevant_text

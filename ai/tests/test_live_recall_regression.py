"""
노드①(회의록 구조화) 실제 API 회수율 회귀 테스트.

## 왜 필요한가

이 파일 이전까지 node1의 테스트는 전부 "구조화된 dict를 넣었을 때
조립 로직이 맞는가"만 검증했다. 노드①이 실제 회의록에서 얼마나
뽑아내는지(회수율)는 아무 자동 테스트도 보지 않았다.

2026-09-16에 실제로 이 문제가 터졌다 — 29,372자짜리 실제 회의록을
같은 코드로 두 번 돌렸는데, 한 번은 회의 후반부(중고 거래·DB 스키마
설계, 전체 분량의 거의 절반)가 통째로 빠졌고 다른 한 번은 잘 잡혔다.
구조화 로직 단위 테스트는 이런 회귀를 절대 잡지 못한다 — 애초에 노드①
자체를 부르지 않기 때문이다.

## 왜 기본으로는 안 도는가

- 실제 OpenAI API를 호출한다(회당 약 0.3~1달러, 약 2~4분).
- STRONG_MODEL(gpt-5)은 temperature=0이어도 완전한 결정론을 보장하지
  않는다 — 실행마다 결과가 정확히 같지 않을 수 있다.

그래서 이 테스트는 RUN_LIVE_API_TESTS=1 환경변수가 있을 때만 돈다.
매 커밋마다 돌릴 필요는 없지만, node.py의 추출·병합·청크 로직을 건드릴
때는 배포 전에 최소 한 번 수동으로 돌려보는 걸 권장한다:

    RUN_LIVE_API_TESTS=1 pytest tests/test_live_recall_regression.py -v
"""

import os
from pathlib import Path

import pytest

from meeting_analysis import node

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "meeting_musinsa_long.txt"

# 어느 필드에서 나오든(problem_items/goals/decisions/requirements/
# unresolved) 상관없다 — 회수율 회귀를 잡는 게 목적이지, 어느 필드에
# 분류됐는지는 이 테스트의 관심사가 아니다. 그룹 안의 키워드 중
# 하나라도 나오면 그 주제는 잡힌 것으로 본다(모델마다 표현이 다를 수
# 있으므로).
EXPECTED_TOPIC_KEYWORDS = {
    "스타일 태깅·분류(회의 전반부)": ["스타일", "태그", "분류"],
    "유튜브 수집·필터링(회의 전반부)": ["유튜브", "필터"],
    "관리자 페이지·지표(회의 중반부)": ["관리자", "지표"],
    # 2026-09-16에 실제로 통째로 누락됐던 후반부 주제. 이 두 그룹이야말로
    # 이 테스트가 지키려는 핵심 회귀 방지선이다.
    "중고·리셀 데이터(회의 후반부)": ["중고", "크림", "유즈드", "리셀", "체결가"],
    "사전·DB 스키마 설계(회의 후반부)": ["사전", "동의어", "테이블"],
}

MIN_EVIDENCE_PASS_RATE = 0.7


def _flatten_text(structured: dict) -> str:
    """구조화 결과 전체를 검색용 텍스트 한 덩어리로 합칩니다."""
    parts: list[str] = []

    project = structured.get("project") or {}
    parts.append(str(project.get("problem", "")))
    for item in project.get("problem_items", []) or []:
        parts.append(str(item.get("content", "")))
    for item in project.get("goals", []) or []:
        parts.append(str(item.get("content", "")))

    for decision in structured.get("decisions", []) or []:
        parts.append(str(decision.get("content", "")))

    requirements = structured.get("requirements", {}) or {}
    for category_items in requirements.values():
        for item in category_items or []:
            parts.append(str(item.get("content", "")))

    for note in structured.get("unresolved", []) or []:
        parts.append(str(note))

    return " ".join(parts)


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_API_TESTS") != "1",
    reason=(
        "실제 OpenAI API를 호출하는 유료·비결정 테스트입니다. "
        "RUN_LIVE_API_TESTS=1로 명시적으로 켜야 실행됩니다."
    ),
)
def test_긴_회의록에서_회의_전체_주제가_회수된다():
    meeting_text = FIXTURE_PATH.read_text(encoding="utf-8")

    result = node.run(meeting_text, meeting_id="live-regression-musinsa")
    combined = _flatten_text(result.data)

    missing = [
        topic
        for topic, keywords in EXPECTED_TOPIC_KEYWORDS.items()
        if not any(keyword in combined for keyword in keywords)
    ]

    assert not missing, (
        f"다음 주제가 구조화 결과에서 전혀 발견되지 않았습니다: {missing}. "
        "회의 후반부가 통째로 누락되는 회귀일 수 있습니다 "
        "(node.py CHUNK_TRIGGER_CHARS·_extract_structured 참고)."
    )

    assert result.evidence.pass_rate >= MIN_EVIDENCE_PASS_RATE, (
        f"근거 통과율이 너무 낮습니다: {result.evidence.pass_rate:.2f}"
    )

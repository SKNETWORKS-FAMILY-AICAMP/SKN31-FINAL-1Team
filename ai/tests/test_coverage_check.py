"""
coverage_check.check_coverage 테스트. LLM을 부르지 않습니다.

## 왜 필요한가

실측으로 확인한 두 가지 문제(같은 회의록·같은 모델·temperature=0인데
목표가 1건 vs 7건으로 갈리는 recall variance, 긴 회의록 청크 병합에서
후반부가 통째로 빠지는 사례)를 프롬프트만으로는 없앨 수 없다. 추출이
끝난 뒤 "요약에 없는 문단이 있는가"만 다시 묻는 저비용 보조 확인을
추가했다. 이 파일은 그 조립 로직(요약 생성, 번호 복원, 실패 시
빈 배열)을 검증한다.
"""

from meeting_analysis.coverage_check import CoverageGaps, _summarize, check_coverage


class _FakeCompletions:
    def __init__(self, numbers):
        self._numbers = list(numbers)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return CoverageGaps(paragraph_numbers=self._numbers)


class _FakeChat:
    def __init__(self, numbers):
        self.completions = _FakeCompletions(numbers)


class _FakeClient:
    def __init__(self, numbers=()):
        self.chat = _FakeChat(numbers)


class _RaisingCompletions:
    def create(self, **kwargs):
        raise RuntimeError("API 장애")


class _RaisingClient:
    def __init__(self):
        self.chat = self
        self.completions = _RaisingCompletions()


def _kwargs():
    return dict(model="gpt-4o", max_retries=3, temperature=0.0, max_tokens=16384)


def test_요약은_content만_모으고_근거_문장은_제외한다():
    data = {
        "project": {
            "problem": "발주 누락",
            "problem_items": [{"content": "문제 A", "evidence": {"quote": "근거 A"}}],
            "goals": [{"content": "목표 A", "evidence": {"quote": "근거 B"}}],
        },
        "requirements": {
            "functional": [{"content": "기능 A"}],
            "technical": [{"content": "기술 A"}],
        },
        "decisions": [{"content": "결정 A"}],
        "constraints": [{"content": "제약 A"}],
        "unresolved": ["미정 A"],
    }

    summary = _summarize(data)

    assert summary == [
        "발주 누락",
        "문제 A",
        "목표 A",
        "기능 A",
        "기술 A",
        "결정 A",
        "제약 A",
        "미정 A",
    ]
    assert "근거 A" not in summary
    assert "근거 B" not in summary


def test_빈_구조화_데이터도_요약이_비지_않고_에러가_나지_않는다():
    assert _summarize({}) == []


FIRST_PARAGRAPH = "이것은 충분히 긴 첫 번째 문단 내용입니다. 짧은 줄 병합 기준을 넘깁니다."
SECOND_PARAGRAPH = "이것은 충분히 긴 두 번째 문단 내용입니다. 이것도 짧은 줄 병합 기준을 넘깁니다."


def test_모델이_고른_번호가_원문_문단으로_복원된다():
    client = _FakeClient(numbers=[2])
    relevant_text = f"{FIRST_PARAGRAPH}\n\n{SECOND_PARAGRAPH}"

    gaps = check_coverage(client, relevant_text, {"project": {}}, **_kwargs())

    assert gaps == [SECOND_PARAGRAPH]


def test_범위를_벗어난_번호는_무시한다():
    client = _FakeClient(numbers=[99])

    gaps = check_coverage(client, FIRST_PARAGRAPH, {"project": {}}, **_kwargs())

    assert gaps == []


def test_빈_번호_배열이면_빈_결과를_반환한다():
    client = _FakeClient(numbers=[])

    gaps = check_coverage(client, FIRST_PARAGRAPH, {"project": {}}, **_kwargs())

    assert gaps == []


def test_원문이_비어있으면_호출조차_하지_않는다():
    client = _FakeClient(numbers=[1])

    gaps = check_coverage(client, "   ", {"project": {}}, **_kwargs())

    assert gaps == []
    assert client.chat.completions.calls == 0


def test_호출이_실패해도_예외를_올리지_않고_빈_결과를_반환한다():
    """
    보조 확인 하나가 실패했다고 노드①의 나머지 결과(추출·근거 검증·
    교차 규칙)까지 막으면 안 된다 — 이 호출은 본 추출이 아니라
    부가 신호다.
    """
    gaps = check_coverage(
        _RaisingClient(), "문단 하나.", {"project": {}}, **_kwargs()
    )

    assert gaps == []

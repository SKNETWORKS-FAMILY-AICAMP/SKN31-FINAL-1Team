"""
노드 ① 청크 병합·중복 제거·길이 기준 분기 테스트.

2026-09-16: 짧은 회의록은 단일 호출, CHUNK_TRIGGER_CHARS를 넘는
회의록만 청크+병합으로 처리하도록 되돌렸다(node.py 모듈 docstring
"길이 기준 하이브리드로 재도입" 참고). 이 파일은 그 분기와, 병합 시
표현만 다른 중복을 유사도로 잡는 동작을 검증한다. 실제 LLM은 부르지
않는다 — client를 가짜로 채워 넣는다.
"""

from shared.schemas_base import Evidence

from meeting_analysis import node
from meeting_analysis.schemas import (
    Decision,
    DecisionCategory,
    MeetingExtraction,
    Project,
    Requirements,
)


def _project(name: str = "테스트") -> Project:
    return Project(
        name=name,
        background="",
        problem="",
        problem_items=[],
        goals=[],
        background_evidence=Evidence(quote="배경 근거 문장"),
        problem_evidence=Evidence(quote="문제 근거 문장"),
    )


def _extraction(decisions: list[Decision]) -> MeetingExtraction:
    return MeetingExtraction(
        project=_project(),
        users=[],
        requirements=Requirements(),
        scenarios=[],
        decisions=decisions,
        constraints=[],
        unresolved=[],
    )


def _decision(content: str, quote: str) -> Decision:
    return Decision(
        category=DecisionCategory.SCOPE,
        content=content,
        rationale="",
        evidence=Evidence(quote=quote),
    )


def test_is_duplicate_잡는_경우_어두_표현_차이():
    """'네.' 같은 어두 표현만 다른 문장은 중복으로 잡는다."""
    a = node._dedupe_key("스토리지랑 AWS, RDS를 나눠서 적재하는 방식으로요.")
    b = node._dedupe_key("네. 스토리지랑 AWS, RDS를 나눠서 적재하는 방식으로요.")

    assert node._is_duplicate(a, [b])


def test_is_duplicate_놓치는_경우_다른_단어():
    """완전히 다른 단어를 쓴 의미상 중복은 문자 유사도로 못 잡는다(알려진 한계)."""
    a = node._dedupe_key("원본은 S3에 저장한다")
    b = node._dedupe_key("원본 데이터는 오브젝트 스토리지에 적재한다")

    assert not node._is_duplicate(a, [b])


def test_is_duplicate_서로_다른_사실은_중복이_아니다():
    a = node._dedupe_key("무신사를 기준 소스로 삼는다")
    b = node._dedupe_key("유튜브 채널 40개를 트래킹한다")

    assert not node._is_duplicate(a, [b])


def test_merge_extractions_유사_표현_결정사항을_하나로_합친다():
    result = _extraction(
        [
            _decision(
                "스토리지랑 RDS를 나눠서 적재한다",
                "스토리지랑 AWS, RDS를 나눠서 적재하는 방식으로요.",
            ),
            _decision(
                "스토리지랑 RDS를 나눠서 적재한다",
                "네. 스토리지랑 AWS, RDS를 나눠서 적재하는 방식으로요.",
            ),
        ]
    )

    merged = node._merge_extractions([result], overview=result)

    assert len(merged["decisions"]) == 1


def test_merge_extractions_overview는_exhaustive_필드에_안_들어간다():
    """overview(전체 원문 통짜 호출)는 project·users 전용이다."""
    chunk_result = _extraction([_decision("청크 결정", "청크 원문 인용문장")])
    overview = _extraction(
        [_decision("오버뷰가 다시 서술한 같은 결정", "오버뷰 원문 인용문장")]
    )

    merged = node._merge_extractions([chunk_result], overview=overview)

    assert len(merged["decisions"]) == 1
    assert merged["decisions"][0]["content"] == "청크 결정"


class _FakeCompletions:
    def __init__(self, result: MeetingExtraction):
        self._result = result
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return self._result


class _FakeChat:
    def __init__(self, result: MeetingExtraction):
        self.completions = _FakeCompletions(result)


class _FakeClient:
    def __init__(self, result: MeetingExtraction):
        self.chat = _FakeChat(result)


def test_짧은_회의록은_단일_호출로_끝난다(monkeypatch):
    monkeypatch.setattr(node, "CHUNK_TRIGGER_CHARS", 100)
    result = _extraction([_decision("결정", "이것은 인용문입니다")])
    client = _FakeClient(result)

    text = "짧은 회의록" * 5  # 100자 이하
    assert len(text) <= 100

    structured = node._extract_structured(client, text, "")

    assert client.chat.completions.calls == 1
    assert structured["decisions"][0]["content"] == "결정"


def test_긴_회의록은_청크로_분할해_여러_번_호출한다(monkeypatch):
    monkeypatch.setattr(node, "CHUNK_TRIGGER_CHARS", 50)
    result = _extraction([_decision("결정", "이것은 인용문입니다")])
    client = _FakeClient(result)

    # chunk_meeting_text의 청크 상한(3,000자)을 넘겨 실제로 청크가
    # 2개 이상 나오게 문단을 충분히 많이 구성합니다.
    text = "\n\n".join(f"이것은 {i}번째 문단 내용입니다. " * 10 for i in range(30))
    assert len(text) > 3000

    node._extract_structured(client, text, "")

    # 청크별 호출(N) + 전체 원문 통짜 호출(1) = N+1번 이상.
    assert client.chat.completions.calls >= 2

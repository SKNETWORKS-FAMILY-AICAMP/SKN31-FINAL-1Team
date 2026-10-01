"""
meeting_analysis.fact_check.check_facts 테스트. LLM을 부르지 않습니다.

## 왜 필요한가

인용문이 원문에 있어도(evidence_status=verified) 그 인용이 항목의
확정적인 서술을 실제로 뒷받침하는지는 별개다. 노드①이 구조화를 마친
뒤 노드②로 넘기기 전에 이걸 확인해 item["context_flag"]를 붙인다.
이 파일은 그 조립 로직(검토 단위 추출, 번호 복원, 인용 재검증,
context_flag 부여, 실패 시 안전한 폴백)을 검증한다.
"""

from meeting_analysis.fact_check import (
    FactCheckFinding,
    FactCheckFindings,
    FactCheckProblemType,
    _build_units,
    check_facts,
)


MEETING_TEXT = (
    "이번 스프린트에서는 결제 기능은 개발 범위에서 제외하기로 확정했습니다. "
    "프론트는 리액트로 갑니다."
)


class _FakeCompletions:
    def __init__(self, findings):
        self._findings = findings
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return FactCheckFindings(findings=self._findings)


class _FakeChat:
    def __init__(self, findings):
        self.completions = _FakeCompletions(findings)


class _FakeClient:
    def __init__(self, findings=()):
        self.chat = _FakeChat(list(findings))


class _RaisingCompletions:
    def create(self, **kwargs):
        raise RuntimeError("API 장애")


class _RaisingClient:
    def __init__(self):
        self.chat = self
        self.completions = _RaisingCompletions()


def _kwargs():
    return dict(model="gpt-4o", max_retries=3, temperature=0.0, max_tokens=16384)


def _data_with_tech_item(content: str) -> dict:
    item = {"content": content, "evidence": {"quote": content}, "evidence_status": "verified"}
    return {
        "project": {"problem_items": [], "goals": []},
        "requirements": {"technical": [item], "functional": [], "non_functional": [], "data": []},
        "decisions": [],
        "constraints": [],
    }


def test_원문에서_확인되는_모순_인용이면_context_flag가_붙는다():
    data = _data_with_tech_item("결제 기능을 자체 구현하여 제공한다.")
    client = _FakeClient(findings=[
        FactCheckFinding(
            unit_id=1,
            problem_type=FactCheckProblemType.CONTRADICTION,
            reason="회의에서 결제 기능을 제외하기로 했는데 기능으로 서술함",
            meeting_quote="결제 기능은 개발 범위에서 제외하기로 확정했습니다",
        )
    ])

    flagged = check_facts(client, data, MEETING_TEXT, **_kwargs())

    assert flagged == 1
    item = data["requirements"]["technical"][0]
    assert "context_flag" in item
    assert "회의 내용과 모순" in item["context_flag"]


def test_원문에_없는_인용은_context_flag를_붙이지_않는다():
    """검증 실패를 자동으로 유효한 근거로 저장하지 않는다."""
    data = _data_with_tech_item("결제 기능을 자체 구현하여 제공한다.")
    client = _FakeClient(findings=[
        FactCheckFinding(
            unit_id=1,
            problem_type=FactCheckProblemType.CONTRADICTION,
            reason="지어낸 근거",
            meeting_quote="회의록에 전혀 없는 문장입니다",
        )
    ])

    flagged = check_facts(client, data, MEETING_TEXT, **_kwargs())

    assert flagged == 0
    assert "context_flag" not in data["requirements"]["technical"][0]


def test_존재하지_않는_번호는_무시된다():
    data = _data_with_tech_item("결제 기능을 자체 구현하여 제공한다.")
    client = _FakeClient(findings=[
        FactCheckFinding(
            unit_id=99,
            problem_type=FactCheckProblemType.CONTRADICTION,
            reason="범위 밖 번호",
            meeting_quote="결제 기능은 개발 범위에서 제외하기로 확정했습니다",
        )
    ])

    flagged = check_facts(client, data, MEETING_TEXT, **_kwargs())

    assert flagged == 0


def test_회의록_원문이_없으면_호출조차_하지_않는다():
    data = _data_with_tech_item("아무 내용")
    client = _FakeClient(findings=[])

    flagged = check_facts(client, data, "   ", **_kwargs())

    assert flagged == 0
    assert client.chat.completions.calls == 0


def test_검토_단위가_없으면_호출하지_않는다():
    data = {
        "project": {"problem_items": [], "goals": []},
        "requirements": {"technical": [], "functional": [], "non_functional": [], "data": []},
        "decisions": [],
        "constraints": [],
    }
    client = _FakeClient(findings=[])

    flagged = check_facts(client, data, MEETING_TEXT, **_kwargs())

    assert flagged == 0
    assert client.chat.completions.calls == 0


def test_호출이_실패해도_예외를_올리지_않고_0을_반환한다():
    data = _data_with_tech_item("아무 내용")

    flagged = check_facts(_RaisingClient(), data, MEETING_TEXT, **_kwargs())

    assert flagged == 0


def test_여러_배열_경로의_검토_단위가_전역_번호로_이어진다():
    data = {
        "project": {
            "problem_items": [{"content": "문제 A"}],
            "goals": [{"content": "목표 A"}],
        },
        "requirements": {
            "technical": [{"content": "기술 A"}],
            "functional": [], "non_functional": [], "data": [],
        },
        "decisions": [{"content": "결정 A"}],
        "constraints": [],
    }

    units = _build_units(data)

    # ARRAY_PATHS 순서: problem_items, goals, functional, non_functional,
    # data, technical, decisions, constraints
    assert [u["text"] for u in units] == ["문제 A", "목표 A", "기술 A", "결정 A"]
    assert [u["id"] for u in units] == [1, 2, 3, 4]


def test_content가_비어있는_항목은_검토_단위에서_제외된다():
    data = {
        "project": {"problem_items": [{"content": "  "}], "goals": []},
        "requirements": {"technical": [], "functional": [], "non_functional": [], "data": []},
        "decisions": [],
        "constraints": [],
    }

    assert _build_units(data) == []

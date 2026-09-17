"""
fact_check.check_facts 테스트. LLM을 부르지 않습니다.

## 왜 필요한가

완성된 기획서 문장이 회의록과 모순되거나 근거 없이 단정하는지 찾는
사실 검토를 추가했다(plan_draft/fact_check.py). 이 파일은 그 조립
로직(섹션별 검토 단위 추출, 번호 복원, 인용 재검증, needs_input용
문구 조립, 실패 시 빈 결과)을 검증한다.
"""

from plan_draft.fact_check import (
    FactCheckFinding,
    FactCheckFindings,
    FactCheckProblemType,
    _build_units,
    check_facts,
)
from plan_draft.schemas import Feature, PlanDocument, PlanSection, SectionType


MEETING_TEXT = (
    "이번 스프린트에서는 결제 기능은 제외하기로 했습니다. "
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


def _tech_scope_document(item_text: str) -> PlanDocument:
    section = PlanSection(
        no=6,
        key="tech_scope",
        title="기술 스택 및 제약사항",
        section_type=SectionType.LIST,
        content_html=f"<ul><li>{item_text}</li></ul>",
        items=[item_text],
    )
    return PlanDocument(
        proposal_id="p1", meeting_id="m1", sections=[section],
    )


def test_원문에서_확인되는_모순_인용은_needs_input에_추가된다():
    document = _tech_scope_document("결제 API 연동을 통해 간편결제를 지원한다.")
    client = _FakeClient(findings=[
        FactCheckFinding(
            unit_id=1,
            problem_type=FactCheckProblemType.CONTRADICTION,
            reason="회의에서 결제 기능을 제외하기로 했는데 기능으로 서술함",
            meeting_quote="결제 기능은 제외하기로 했습니다",
        )
    ])

    notes = check_facts(client, document, MEETING_TEXT, **_kwargs())

    assert "tech_scope" in notes
    assert "사실 검토 필요" in notes["tech_scope"][0]
    assert "회의 내용과 모순" in notes["tech_scope"][0]
    assert "결제 기능은 제외하기로 했습니다" in notes["tech_scope"][0]


def test_원문에_없는_인용은_폐기된다():
    """검증 실패를 자동으로 유효한 근거로 저장하지 않는다."""
    document = _tech_scope_document("결제 API 연동을 통해 간편결제를 지원한다.")
    client = _FakeClient(findings=[
        FactCheckFinding(
            unit_id=1,
            problem_type=FactCheckProblemType.CONTRADICTION,
            reason="지어낸 근거",
            meeting_quote="회의록에 전혀 없는 문장입니다",
        )
    ])

    notes = check_facts(client, document, MEETING_TEXT, **_kwargs())

    assert notes == {}


def test_존재하지_않는_번호는_폐기된다():
    document = _tech_scope_document("결제 API 연동을 통해 간편결제를 지원한다.")
    client = _FakeClient(findings=[
        FactCheckFinding(
            unit_id=99,
            problem_type=FactCheckProblemType.CONTRADICTION,
            reason="범위 밖 번호",
            meeting_quote="결제 기능은 제외하기로 했습니다",
        )
    ])

    notes = check_facts(client, document, MEETING_TEXT, **_kwargs())

    assert notes == {}


def test_회의록_원문이_없으면_호출조차_하지_않는다():
    document = _tech_scope_document("아무 내용")
    client = _FakeClient(findings=[
        FactCheckFinding(
            unit_id=1,
            problem_type=FactCheckProblemType.CONTRADICTION,
            reason="사유",
            meeting_quote="아무 인용",
        )
    ])

    notes = check_facts(client, document, "   ", **_kwargs())

    assert notes == {}
    assert client.chat.completions.calls == 0


def test_검토_단위가_없으면_호출하지_않는다():
    empty_section = PlanSection(
        no=6, key="tech_scope", title="기술 스택 및 제약사항",
        section_type=SectionType.LIST, content_html="", items=[],
    )
    document = PlanDocument(proposal_id="p1", meeting_id="m1", sections=[empty_section])
    client = _FakeClient(findings=[])

    notes = check_facts(client, document, MEETING_TEXT, **_kwargs())

    assert notes == {}
    assert client.chat.completions.calls == 0


def test_호출이_실패해도_예외를_올리지_않고_빈_결과를_반환한다():
    document = _tech_scope_document("아무 내용")

    notes = check_facts(_RaisingClient(), document, MEETING_TEXT, **_kwargs())

    assert notes == {}


def test_서술형_섹션은_p태그_단위로_검토_단위가_나뉜다():
    section = PlanSection(
        no=1, key="overview", title="프로젝트 개요",
        section_type=SectionType.NARRATIVE,
        content_html="<p>첫 번째 문단입니다.</p><p>두 번째 문단입니다.</p>",
    )
    document = PlanDocument(proposal_id="p1", meeting_id="m1", sections=[section])

    units = _build_units(document)

    assert [u["text"] for u in units] == ["첫 번째 문단입니다.", "두 번째 문단입니다."]
    assert all(u["section_key"] == "overview" for u in units)


def test_features_섹션은_제목과_설명으로_검토_단위가_만들어진다():
    section = PlanSection(
        no=5, key="features", title="주요 기능",
        section_type=SectionType.NARRATIVE,
        content_html="",
        features=[Feature(group="mvp", title="알림", description="푸시 알림을 보낸다.")],
    )
    document = PlanDocument(proposal_id="p1", meeting_id="m1", sections=[section])

    units = _build_units(document)

    assert units == [{"id": 1, "section_key": "features", "text": "알림: 푸시 알림을 보낸다."}]


def test_여러_섹션의_검토_단위는_전역_번호로_이어진다():
    tech = PlanSection(
        no=6, key="tech_scope", title="기술 스택 및 제약사항",
        section_type=SectionType.LIST, content_html="", items=["항목 A", "항목 B"],
    )
    decisions = PlanSection(
        no=7, key="decisions", title="최종 결정사항",
        section_type=SectionType.LIST, content_html="", items=["결정 A"],
    )
    document = PlanDocument(proposal_id="p1", meeting_id="m1", sections=[tech, decisions])

    units = _build_units(document)

    assert [u["id"] for u in units] == [1, 2, 3]
    assert [u["section_key"] for u in units] == ["tech_scope", "tech_scope", "decisions"]


def test_기존_needs_input이_있어도_그대로_반환되고_호출부가_이어붙인다():
    """check_facts 자체는 needs_input을 건드리지 않는다 — 병합은 agent.py의 몫이다."""
    section = PlanSection(
        no=6, key="tech_scope", title="기술 스택 및 제약사항",
        section_type=SectionType.LIST, content_html="", items=["항목 A"],
        needs_input="기존 확인 문구",
    )
    document = PlanDocument(proposal_id="p1", meeting_id="m1", sections=[section])
    client = _FakeClient(findings=[
        FactCheckFinding(
            unit_id=1,
            problem_type=FactCheckProblemType.UNSUPPORTED_CLAIM,
            reason="근거 없음",
            meeting_quote="프론트는 리액트로 갑니다",
        )
    ])

    notes = check_facts(client, document, MEETING_TEXT, **_kwargs())

    assert section.needs_input == "기존 확인 문구"  # 원본은 그대로
    assert "tech_scope" in notes

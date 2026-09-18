"""사용자 단서 전달과 근거 표시 회귀 테스트. 외부 모델은 호출하지 않습니다."""

from meeting_analysis.node import _merge_extractions
from meeting_analysis.schemas import MeetingExtraction
from meeting_analysis.validators.evidence import verify_and_mark
from plan_draft import agent
from plan_draft.list_builder import build_user_citation_sources
from plan_draft.prompts import _build_generation_payload
from plan_draft.schemas import NarrativeSection, PlanSections, SECTION_SPEC


def signal(content, status="stated"):
    return {
        "kind": "service_purpose", "actor": "", "content": content,
        "statement_status": status, "evidence": {"quote": content},
    }


def extraction(signals=()):
    return MeetingExtraction.model_validate({
        "project": {
            "name": "test", "background": "", "problem": "",
            "background_evidence": {"quote": "테스트 배경 근거"},
            "problem_evidence": {"quote": "테스트 문제 근거"},
        }, "requirements": {}, "user_signals": list(signals),
    })


def test_legacy_input_and_overview_merge():
    assert extraction().user_signals == []
    overview = extraction([signal("주목적은 트렌드 분석이다.")])
    chunk = extraction([signal("가격 비교가 주목적이다.")])
    merged = _merge_extractions([chunk], overview)
    assert merged["user_signals"] == overview.model_dump()["user_signals"]


def test_quote_verification_and_payload_preserve_context():
    raw = "주목적은 트렌드 분석이다. 최저가 추천인가요?"
    data = {"user_signals": [
        signal("주목적은 트렌드 분석이다."),
        signal("최저가 추천인가요?", "question"),
        signal("근거 없는 할인 추천"),
    ]}
    report = verify_and_mark(data, raw)
    assert report.verified_count == 2
    data["user_signals"][1]["context_flag"] = "질문을 결정으로 쓰지 않음"
    sources = _build_generation_payload(data)["user_sources_for_citation"]
    assert len(sources) == 2
    assert sources[1]["statement_status"] == "question"
    assert sources[1]["quote"] == "최저가 추천인가요?"
    assert sources[1]["context_flag"]
    assert build_user_citation_sources({}) == []


def test_multiple_quotes_warnings_and_regeneration(monkeypatch):
    data = {"users": [], "user_signals": [
        signal("트렌드 분석이 목적이다."), signal("가격 비교를 제안한다.", "proposed"),
    ]}
    verify_and_mark(data, "트렌드 분석이 목적이다. 가격 비교를 제안한다.")
    data["user_signals"][1]["context_flag"] = "<미확정>"
    gen = NarrativeSection(
        key="users", content_html="<p>활용 제안</p>",
        source_indices=[0, 1, 1, 999], needs_input="이용 범위 확인",
    )
    spec = next(s for s in SECTION_SPEC if s["key"] == "users")
    initial = agent._build_users_section(gen, data, spec)
    assert len(initial.evidence) == 2
    assert agent.AI_SUGGESTED_SECTION_NOTE in initial.content_html
    assert "인용 번호" in initial.needs_input
    assert "&lt;미확정&gt;" in initial.content_html
    assert "제안·질문·철회" in initial.needs_input
    monkeypatch.setattr(agent, "_call", lambda *a, **kw: PlanSections(sections=[gen]))
    regenerated = agent.regenerate_section(data, "users", "content", "보완")
    assert regenerated.model_dump() == initial.model_dump()

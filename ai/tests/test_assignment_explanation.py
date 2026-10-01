"""
tests/test_assignment_explanation.py

2026-09-11 (Phase 4 item 13): 계획 브리핑 LLM 에이전트.
LLM 호출은 monkeypatch로 대체 — graceful 실패와 통과만 본다.
"""

from assignment_explanation import agent as expl_agent
from assignment_explanation.agent import summarize_plan
from assignment_explanation.schemas import PlanBriefing


def test_returns_briefing_on_success(monkeypatch):
    monkeypatch.setattr(
        expl_agent, "create_structured",
        lambda **kw: PlanBriefing(risks=["결제 정책 미확정"], checkpoints=["9/7까지 정책 확인"]),
    )
    out = summarize_plan({"total_units": 5})
    assert out.risks == ["결제 정책 미확정"]
    assert out.checkpoints == ["9/7까지 정책 확인"]


def test_llm_failure_returns_empty_briefing(monkeypatch):
    def boom(**kw):
        raise RuntimeError("api down")
    monkeypatch.setattr(expl_agent, "create_structured", boom)
    out = summarize_plan({"total_units": 5})
    assert isinstance(out, PlanBriefing)
    assert out.risks == [] and out.checkpoints == []

"""
tests/test_candidate_fit.py

2026-09-11: assignment_ranking.score_candidate_fit — 후보 질적 적합도 판단.
LLM 호출은 monkeypatch로 대체한다 — 사전 필터·폴백·graceful 실패만 결정적으로 본다.
"""

from assignment_ranking import agent as ranking_agent
from assignment_ranking.agent import _candidates_for_unit, score_candidate_fit
from assignment_ranking.schemas import CandidateFitBatch, CandidateFitScore, UnitCandidateFit


def _unit(uid, skills, hours=6.0):
    return {"unit_id": uid, "title": uid, "description": "d", "required_skills": skills, "estimated_hours": hours}


def _member(eid, skills, levels=None):
    return {"employee_id": eid, "skills": skills, "skill_levels": levels or {},
            "certifications": [], "past_similar_tasks": []}


# ---------------------------------------------------------------------------
# _candidates_for_unit — 정적 스킬 풀 (용량 무시)
# ---------------------------------------------------------------------------
def test_candidates_filtered_by_skill_overlap():
    members = [_member("a", ["Django"]), _member("b", ["React"])]
    out = _candidates_for_unit(_unit("T1", ["Django"]), members)
    assert [m["employee_id"] for m in out] == ["a"]


def test_no_required_skills_returns_all_members():
    members = [_member("a", ["Django"]), _member("b", ["React"])]
    out = _candidates_for_unit(_unit("T1", []), members)
    assert len(out) == 2


# ---------------------------------------------------------------------------
# score_candidate_fit — 사전 필터 + 배치 + graceful 실패
# ---------------------------------------------------------------------------
def test_unit_with_single_candidate_skips_llm(monkeypatch):
    called = []
    monkeypatch.setattr(ranking_agent, "create_structured", lambda **kw: called.append(1) or CandidateFitBatch())
    units = [_unit("T1", ["Django"])]
    members = [_member("a", ["Django"])]  # 후보 1명뿐 -> 판단 무의미
    out = score_candidate_fit(units, members)
    assert out == {}
    assert called == []


def test_llm_scores_are_returned_per_unit(monkeypatch):
    batch = CandidateFitBatch(units=[
        UnitCandidateFit(unit_id="T1", candidates=[
            CandidateFitScore(employee_id="a", fit_score=0.3, reason="관련 경험 적음"),
            CandidateFitScore(employee_id="b", fit_score=0.9, reason="동일 업무 수행 경험 있음"),
        ])
    ])
    monkeypatch.setattr(ranking_agent, "create_structured", lambda **kw: batch)
    units = [_unit("T1", ["Django"])]
    members = [_member("a", ["Django"]), _member("b", ["Django"])]
    out = score_candidate_fit(units, members)
    assert out["T1"]["a"]["score"] == 0.3
    assert out["T1"]["b"]["reason"] == "동일 업무 수행 경험 있음"


def test_llm_failure_returns_empty_and_does_not_raise(monkeypatch):
    def boom(**kw):
        raise RuntimeError("api down")
    monkeypatch.setattr(ranking_agent, "create_structured", boom)
    units = [_unit("T1", ["Django"])]
    members = [_member("a", ["Django"]), _member("b", ["Django"])]
    assert score_candidate_fit(units, members) == {}

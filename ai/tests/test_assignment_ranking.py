"""
tests/test_assignment_ranking.py

2026-09-11 (Phase 3 item 10-11): WorkPackage 분할 판단.
LLM 호출은 monkeypatch로 대체한다 — 사전 필터·폴백·graceful 실패만 결정적으로 본다.
"""

import pytest

from assignment_ranking import agent as ranking_agent
from assignment_ranking.agent import _package_needs_llm, decide_package_splits
from assignment_ranking.schemas import PackageSplitBatch, PackageSplitDecision


def _u(uid, skills, req="FR-01", hours=6.0):
    return {"unit_id": uid, "title": uid, "required_skills": skills,
            "estimated_hours": hours, "source_req_id": req}


def _pkg(pid, unit_ids, hours=12.0, reqs=("FR-01",)):
    return {"package_id": pid, "feature_area": "결제", "unit_ids": list(unit_ids),
            "estimated_hours": hours, "source_req_ids": list(reqs)}


# ---------------------------------------------------------------------------
# 사전 필터
# ---------------------------------------------------------------------------
def test_single_unit_package_never_asks_llm():
    assert _package_needs_llm(_pkg("WP-001", ["A"]), [_u("A", ["Django"])], 300) is False


def test_single_role_small_package_does_not_need_llm():
    units = [_u("A", ["Django"]), _u("B", ["Django"])]
    assert _package_needs_llm(_pkg("WP-001", ["A", "B"], hours=12), units, 300) is False


def test_multi_role_package_needs_llm():
    units = [_u("A", ["React"]), _u("B", ["Django"])]
    assert _package_needs_llm(_pkg("WP-001", ["A", "B"]), units, 300) is True


def test_oversized_package_needs_llm():
    units = [_u("A", ["Django"], hours=200), _u("B", ["Django"], hours=200)]
    assert _package_needs_llm(_pkg("WP-001", ["A", "B"], hours=400), units, 300) is True


# ---------------------------------------------------------------------------
# decide_package_splits
# ---------------------------------------------------------------------------
def test_no_ambiguous_package_skips_llm_entirely(monkeypatch):
    called = []
    monkeypatch.setattr(ranking_agent, "create_structured",
                        lambda **kw: called.append(1) or PackageSplitBatch())
    packages = [_pkg("WP-001", ["A", "B"], hours=12)]
    units_by_id = {"A": _u("A", ["Django"]), "B": _u("B", ["Django"])}
    out = decide_package_splits(packages, units_by_id, 300)
    assert out == {}
    assert called == []  # LLM 미호출


def test_llm_split_true_is_returned_false_is_dropped(monkeypatch):
    batch = PackageSplitBatch(decisions=[
        PackageSplitDecision(package_id="WP-001", split=True, reason="역할이 섞임"),
        PackageSplitDecision(package_id="WP-002", split=False),
    ])
    monkeypatch.setattr(ranking_agent, "create_structured", lambda **kw: batch)
    packages = [
        _pkg("WP-001", ["A", "B"]),  # multi-role -> asked
        _pkg("WP-002", ["C", "D"]),  # multi-role -> asked
    ]
    units_by_id = {
        "A": _u("A", ["React"]), "B": _u("B", ["Django"]),
        "C": _u("C", ["React"]), "D": _u("D", ["Django"]),
    }
    out = decide_package_splits(packages, units_by_id, 300)
    assert set(out) == {"WP-001"}
    assert out["WP-001"]["reason"] == "역할이 섞임"


def test_llm_failure_returns_empty(monkeypatch):
    def boom(**kw):
        raise RuntimeError("api down")
    monkeypatch.setattr(ranking_agent, "create_structured", boom)
    packages = [_pkg("WP-001", ["A", "B"])]
    units_by_id = {"A": _u("A", ["React"]), "B": _u("B", ["Django"])}
    assert decide_package_splits(packages, units_by_id, 300) == {}

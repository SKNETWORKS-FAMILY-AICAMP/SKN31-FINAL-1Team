"""
tests/test_a2_3.py

2026-09-11 (Phase 3): assignee_recommend 스킬 매칭이 숙련도(proficiency)를
반영하는지. 순수 계산이라 결정적으로 확인한다.
"""

from assignee_recommend.rule_filter import _fit_score, _match_skills, schedule_assignments, sort_units_by_priority


def _unit(uid, skills, req="FR-01", hours=6.0):
    return {
        "unit_id": uid, "parent_task_id": None, "title": uid, "description": "d",
        "required_skills": skills, "estimated_hours": hours, "source_req_id": req,
        "depends_on": [], "risk_buffer_factor": None, "feature_area": None,
    }


def _member(eid, skills, levels=None):
    return {
        "employee_id": eid,
        "skills": skills,
        "skill_levels": levels or {},
        "past_similar_tasks": [],
        "certifications": [],
    }


# ---------------------------------------------------------------------------
# _match_skills
# ---------------------------------------------------------------------------
def test_match_returns_member_level():
    matched = _match_skills({"Django"}, {"Django"}, {"Django": 4})
    assert matched == {"Django": 4}


def test_match_fuzzy_keeps_level():
    # "REST API 설계"(required) ↔ "REST API"(member) 접미어 제거 후 일치
    matched = _match_skills({"REST API 설계"}, {"REST API"}, {"REST API": 5})
    assert matched == {"REST API 설계": 5}


def test_match_defaults_to_mid_level_without_level_info():
    matched = _match_skills({"Django"}, {"Django"})
    assert matched == {"Django": 3}


def test_unmatched_required_is_absent():
    matched = _match_skills({"Django", "Kubernetes"}, {"Django"}, {"Django": 2})
    assert matched == {"Django": 2}


# ---------------------------------------------------------------------------
# schedule_assignments: 숙련도가 배정 순위를 가른다
# ---------------------------------------------------------------------------
def test_higher_proficiency_wins_when_other_factors_equal():
    units = sort_units_by_priority([_unit("T1", ["Django"])], {"FR-01": "High"})
    members = [
        _member("junior", ["Django"], {"Django": 2}),
        _member("senior", ["Django"], {"Django": 5}),
    ]
    result = schedule_assignments(units, members, {}, max_hours_per_assignee=200.0, total_workdays=100)
    assert result[0]["employee_id"] == "senior"


def test_without_levels_falls_back_to_presence_and_still_assigns():
    units = sort_units_by_priority([_unit("T1", ["Django"])], {"FR-01": "High"})
    members = [_member("a", ["Django"]), _member("b", ["Django"])]
    result = schedule_assignments(units, members, {}, max_hours_per_assignee=200.0, total_workdays=100)
    assert result[0]["employee_id"] in {"a", "b"}  # 죽지 않고 배정됨


def test_reason_text_shows_level_when_available():
    units = sort_units_by_priority([_unit("T1", ["Django"])], {"FR-01": "High"})
    members = [_member("senior", ["Django"], {"Django": 5})]
    result = schedule_assignments(units, members, {}, max_hours_per_assignee=200.0, total_workdays=100)
    assert "Lv5" in result[0]["skill_match"]


# ---------------------------------------------------------------------------
# 2026-09-11: 후보 질적 적합도(fit_scores) — LLM이 경력·자격증 내용을 판단한
# 점수를 _fit_score/schedule_assignments가 어떻게 쓰는지.
# ---------------------------------------------------------------------------
def test_fit_score_fallback_matches_old_count_based_formula():
    unit = _unit("T1", ["Django"])
    member = {"skill_levels": {}, "past_similar_tasks": ["a", "b", "c"], "certifications": ["x", "y"]}
    matched = {"Django": 3}
    # qualitative_fit 없이 호출 -> 기존 0.15*min(sim/3,1) + 0.10*min(cert/2,1) 과 대수적으로 동일해야 함
    got = _fit_score(unit, member, matched, remaining_ratio=0.5, already_on_same_package=False)
    expected = round(0.40 * 1.0 + 0.25 * (0.6 * 1.0 + 0.4 * 1.0) + 0.15 * 0.5 + 0.20 * 0.0, 3)
    assert got == expected


def test_qualitative_fit_overrides_count_based_score():
    unit = _unit("T1", ["Django"])
    matched = {"Django": 3}
    no_history = {"skill_levels": {}, "past_similar_tasks": [], "certifications": []}
    low = _fit_score(unit, no_history, matched, 0.5, False, qualitative_fit=0.1)
    high = _fit_score(unit, no_history, matched, 0.5, False, qualitative_fit=0.9)
    assert high > low  # 개수 기반이면 둘 다 0점일 상황인데, 질적 점수가 갈라놓는다


def test_schedule_assignments_prefers_higher_qualitative_fit_on_tie():
    # 스킬·레벨·여유 전부 동률 -> 순수하게 fit_scores 차이로 갈린다
    units = sort_units_by_priority([_unit("T1", ["Django"])], {"FR-01": "High"})
    members = [
        _member("a", ["Django"], {"Django": 3}),
        _member("b", ["Django"], {"Django": 3}),
    ]
    fit_scores = {"T1": {"a": {"score": 0.2, "reason": "관련 경험 없음"},
                          "b": {"score": 0.95, "reason": "동일한 결제 연동 프로젝트 수행 경험"}}}
    result = schedule_assignments(units, members, {}, max_hours_per_assignee=200.0, total_workdays=100, fit_scores=fit_scores)
    assert result[0]["employee_id"] == "b"
    assert result[0]["similar_experience"] == "동일한 결제 연동 프로젝트 수행 경험"


def test_schedule_assignments_without_fit_scores_falls_back_to_count_text():
    units = sort_units_by_priority([_unit("T1", ["Django"])], {"FR-01": "High"})
    members = [_member("a", ["Django"], {"Django": 3})]
    result = schedule_assignments(units, members, {}, max_hours_per_assignee=200.0, total_workdays=100)
    assert "유사 업무 완료 이력" in result[0]["similar_experience"]

"""
tests/test_team_sizing.py

LLM 호출이 없는 순수 계산 모듈이라 전부 즉시 실행 가능하다(수동 실행 스크립트 불필요).
"""

import pytest

from team_sizing import build_skill_role_map, estimate_team_size


def _emp(role, skills, active=True):
    return {"is_active": active, "job_role": role, "skills": skills}


# ---------------------------------------------------------------------------
# build_skill_role_map — 인력에서 skill -> {role: weight} 도출
# ---------------------------------------------------------------------------
def test_skill_maps_to_the_only_role_that_has_it():
    profs = [_emp("BACKEND", ["Django"]), _emp("BACKEND", ["Django"])]
    assert build_skill_role_map(profs) == {"Django": {"BACKEND": 1.0}}


def test_skill_held_by_two_roles_is_weighted():
    profs = [_emp("BACKEND", ["Python"])] * 3 + [_emp("DATA_ENGINEER", ["Python"])] * 1
    m = build_skill_role_map(profs)
    assert m["Python"] == {"BACKEND": 0.75, "DATA_ENGINEER": 0.25}


def test_minor_role_below_threshold_is_dropped():
    # DEVOPS가 1/10 = 0.1 < 0.15 -> 버려지고 나머지가 재정규화된다
    profs = [_emp("BACKEND", ["Redis"])] * 6 + [_emp("DATA_ENGINEER", ["Redis"])] * 3 + [_emp("DEVOPS", ["Redis"])] * 1
    m = build_skill_role_map(profs)
    assert set(m["Redis"]) == {"BACKEND", "DATA_ENGINEER"}
    assert abs(sum(m["Redis"].values()) - 1.0) < 1e-6


def test_pm_and_fullstack_excluded():
    profs = [_emp("PROJECT_MANAGER", ["Jira"]), _emp("FULLSTACK", ["Vue"])]
    assert build_skill_role_map(profs) == {}


def test_inactive_excluded():
    assert build_skill_role_map([_emp("BACKEND", ["Django"], active=False)]) == {}


def test_estimate_uses_derived_map():
    tasks = [_task("TASK-001", ["Python"], 80)]
    derived = {"Python": {"BACKEND": 0.75, "DATA_ENGINEER": 0.25}}
    est = estimate_team_size(tasks, "2026-09-07", "2026-09-11", skill_role_map=derived)["team_size_estimate"]
    by_role = {r["role"]: r["estimated_hours"] for r in est["by_role"]}
    assert by_role == {"BACKEND": 60.0, "DATA_ENGINEER": 20.0}


def test_skill_nobody_has_becomes_unmapped():
    tasks = [_task("TASK-001", ["Rust"], 40)]
    est = estimate_team_size(tasks, "2026-09-07", "2026-09-11", skill_role_map={})["team_size_estimate"]
    assert est["by_role"][0]["role"] == "미분류"


def _task(task_id, skills, hours, req_id="FR-01-001"):
    return {
        "task_id": task_id,
        "title": task_id,
        "description": "d",
        "required_skills": skills,
        "estimated_hours": hours,
        "source_req_id": req_id,
        "subtasks": [],
    }


def test_single_role_headcount():
    # 평일 5일(월~금) x 8시간 = 상한 40시간. backend 80시간짜리 업무 -> 2명.
    tasks = [_task("TASK-001", ["Django"], 80)]
    result = estimate_team_size(tasks, "2026-09-07", "2026-09-11")  # 월~금
    est = result["team_size_estimate"]
    assert est["assumptions"]["max_hours_per_assignee"] == 40.0
    assert est["by_role"] == [{"role": "BACKEND", "estimated_hours": 80.0, "headcount": 2}]
    assert est["total_headcount"] == 2


def test_multi_role_skill_splits_hours_proportionally():
    # ["Django", "MySQL"]인 8시간짜리 업무 -> BACKEND 4h, DATA_ENGINEER 4h로 절반씩.
    tasks = [_task("TASK-001", ["Django", "MySQL"], 8)]
    result = estimate_team_size(tasks, "2026-09-07", "2026-09-11")
    by_role = {r["role"]: r["estimated_hours"] for r in result["team_size_estimate"]["by_role"]}
    assert by_role == {"BACKEND": 4.0, "DATA_ENGINEER": 4.0}


def test_unmapped_skill_falls_back_to_unmapped_role():
    tasks = [_task("TASK-001", ["아무도 모르는 스킬"], 8)]
    result = estimate_team_size(tasks, "2026-09-07", "2026-09-11")
    assert result["team_size_estimate"]["by_role"][0]["role"] == "미분류"


def test_subtasks_used_instead_of_parent_task():
    # 3원칙 미충족으로 쪼개진 Task는 subtasks만 배정 단위 -> 부모 Task의 estimated_hours는
    # 이중 계산되면 안 된다(flatten_assignable_units 재사용 검증).
    task = _task("TASK-001", ["Django"], 999)  # 부모 값은 무시돼야 함
    task["subtasks"] = [
        {"subtask_id": "SUBTASK-001-1", "title": "s1", "description": "d", "estimated_hours": 4},
        {"subtask_id": "SUBTASK-001-2", "title": "s2", "description": "d", "estimated_hours": 4},
    ]
    result = estimate_team_size([task], "2026-09-07", "2026-09-11")
    by_role = {r["role"]: r["estimated_hours"] for r in result["team_size_estimate"]["by_role"]}
    assert by_role == {"BACKEND": 8.0}


def test_ceil_overestimation_is_visible_per_role():
    # 각각 5시간짜리(상한 40시간 대비 극소량) 업무가 서로 다른 두 역할이면, 실제 합은
    # 10시간(0.25명 분)인데 role별로 올림해서 총 2명으로 과대추정됨 — 의도된 동작.
    tasks = [_task("TASK-001", ["Django"], 5), _task("TASK-002", ["React"], 5)]
    result = estimate_team_size(tasks, "2026-09-07", "2026-09-11")
    assert result["team_size_estimate"]["total_headcount"] == 2


def test_invalid_date_range_raises():
    with pytest.raises(ValueError):
        estimate_team_size([_task("TASK-001", ["Django"], 8)], "2026-09-11", "2026-09-07")

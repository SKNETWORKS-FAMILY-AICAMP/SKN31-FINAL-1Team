"""
tests/test_assignee_mapping_filter.py

assignee_mapping/rule_filter.py의 후보 필터링 — LLM 호출이 없는 순수 로직이라
즉시 실행 가능하다.
"""

from assignee_mapping.rule_filter import filter_candidates
from assignee_mapping.schemas import RawEmployeeProfile

TASKS = [{"task_id": "TASK-001", "required_skills": ["Django", "REST API"], "estimated_hours": 8}]
NEEDED_ROLES = ["BACKEND"]


def _profile(**overrides):
    base = dict(
        employee_id="EMP-001",
        employee_no="1",
        name="테스트",
        job_role="BACKEND",
        is_active=True,
        skills=["Django"],
        certifications=[],
        career_history_text="",
    )
    base.update(overrides)
    return RawEmployeeProfile(**base)


def test_passes_all_conditions():
    result = filter_candidates([_profile()], TASKS, NEEDED_ROLES)
    assert [p.employee_id for p in result] == ["EMP-001"]


def test_excludes_inactive():
    result = filter_candidates([_profile(is_active=False)], TASKS, NEEDED_ROLES)
    assert result == []


def test_excludes_unneeded_role():
    result = filter_candidates([_profile(job_role="UIUX_DESIGNER")], TASKS, NEEDED_ROLES)
    assert result == []


def test_excludes_no_skill_overlap():
    result = filter_candidates([_profile(skills=["React"])], TASKS, NEEDED_ROLES)
    assert result == []


def test_keeps_partial_skill_overlap():
    # 요구 기술 전부는 아니어도 하나라도 겹치면 통과
    result = filter_candidates([_profile(skills=["Django", "React"])], TASKS, NEEDED_ROLES)
    assert len(result) == 1

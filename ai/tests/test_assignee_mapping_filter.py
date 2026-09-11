"""
tests/test_assignee_mapping_filter.py

assignee_mapping/rule_filter.filter_candidates — LLM 없는 순수 로직.

2026-09-11: 직무(needed_roles) 게이트를 제거했다. 자격 판정은 "재직 중" + "필요
스킬을 하나라도 보유" 두 조건뿐이다.
"""

from assignee_mapping.rule_filter import filter_candidates
from assignee_mapping.schemas import RawEmployeeProfile

TASKS = [{"task_id": "TASK-001", "required_skills": ["Django", "REST API"], "estimated_hours": 8}]


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


def test_active_with_matching_skill_passes():
    result = filter_candidates([_profile()], TASKS)
    assert [p.employee_id for p in result] == ["EMP-001"]


def test_excludes_inactive():
    assert filter_candidates([_profile(is_active=False)], TASKS) == []


def test_excludes_no_skill_overlap():
    assert filter_candidates([_profile(skills=["React"])], TASKS) == []


def test_keeps_partial_skill_overlap():
    # 요구 기술 전부는 아니어도 하나라도 겹치면 통과
    result = filter_candidates([_profile(skills=["Django", "React"])], TASKS)
    assert len(result) == 1


def test_job_role_is_irrelevant():
    # 직무가 뭐든 스킬만 맞으면 후보다 — team_sizing 매핑이 비어도 배분이 안 죽는다
    result = filter_candidates([_profile(job_role="UIUX_DESIGNER", skills=["Django"])], TASKS)
    assert [p.employee_id for p in result] == ["EMP-001"]


def test_needed_roles_arg_is_accepted_but_ignored():
    # 옛 호출부 호환: 3번째 인자를 줘도 결과가 달라지지 않는다
    a = filter_candidates([_profile(job_role="DATA_ENGINEER")], TASKS)
    b = filter_candidates([_profile(job_role="DATA_ENGINEER")], TASKS, ["BACKEND"])
    assert [p.employee_id for p in a] == [p.employee_id for p in b] == ["EMP-001"]


def test_no_required_skills_keeps_all_active():
    tasks = [{"task_id": "T", "required_skills": [], "estimated_hours": 4}]
    result = filter_candidates([_profile(), _profile(employee_id="EMP-002", is_active=False)], tasks)
    assert [p.employee_id for p in result] == ["EMP-001"]

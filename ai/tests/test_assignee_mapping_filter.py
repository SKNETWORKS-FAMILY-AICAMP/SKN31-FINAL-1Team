"""
tests/test_assignee_mapping_filter.py

assignee_mapping/rule_filter.filter_candidates — LLM 없는 순수 로직.

2026-09-11: 직무(needed_roles) 게이트를 제거했다. 자격 판정은 "재직 중" + "필요
스킬을 하나라도 보유" 두 조건뿐이다 — 단, 2026-09-18부터 PROJECT_MANAGER는 스킬
매칭 여부와 무관하게 예외로 제외한다("PM은 개발 프로젝트에 참여하지 않는다"는
팀 원칙; 위 게이트 제거 때 같이 빠졌던 걸 되살림).
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


def test_excludes_project_manager():
    # 2026-09-18: PM은 스킬이 겹쳐도 후보에서 무조건 빠져야 한다. PM은 개발 프로젝트에 참여하지 않는다" 팀 원칙).
    result = filter_candidates([_profile(job_role="PROJECT_MANAGER", skills=["Django"])], TASKS)
    assert result == []


def test_needed_roles_arg_is_accepted_but_ignored():
    # 옛 호출부 호환: 3번째 인자를 줘도 결과가 달라지지 않는다
    a = filter_candidates([_profile(job_role="DATA_ENGINEER")], TASKS)
    b = filter_candidates([_profile(job_role="DATA_ENGINEER")], TASKS, ["BACKEND"])
    assert [p.employee_id for p in a] == [p.employee_id for p in b] == ["EMP-001"]


def test_no_required_skills_keeps_all_active():
    tasks = [{"task_id": "T", "required_skills": [], "estimated_hours": 4}]
    result = filter_candidates([_profile(), _profile(employee_id="EMP-002", is_active=False)], tasks)
    assert [p.employee_id for p in result] == ["EMP-001"]


# ---------------------------------------------------------------------------
# 2026-09-14: 역할별 후보 상한 — current_workload/total_workdays/skill_role_map을
# 셋 다 줘야 적용된다. 하나라도 없으면 위 테스트들처럼 스킬 겹침만으로 거른다.
# ---------------------------------------------------------------------------

ROLE_TASKS = [
    {
        "task_id": "T1",
        "title": "t",
        "description": "d",
        "source_req_id": "FR-01-001",
        "required_skills": ["Django"],
        "estimated_hours": 48,
    }
]
ROLE_MAP = {"Django": {"BACKEND": 1.0}}


def test_role_cap_without_new_args_keeps_everyone():
    # 새 kwargs를 안 주면(호출부 미대응) 상한 없이 예전처럼 전부 통과.
    profiles = [_profile(employee_id=f"EMP-{i}", skills=["Django"]) for i in range(7)]
    result = filter_candidates(profiles, ROLE_TASKS)
    assert len(result) == 7


def test_role_cap_skipped_when_only_current_workload_is_missing():
    # 2026-09-15: skill_role_map/total_workdays는 줬지만 current_workload만 None이면
    # (문서·호출부 주석이 약속한 대로) 상한 자체를 건너뛰어야 한다 — current_workload를
    # {}로 취급해 캡을 계속 적용하면 "셋 다 있어야 적용" 계약이 깨진다.
    profiles = [_profile(employee_id=f"EMP-{i}", skills=["Django"]) for i in range(7)]
    result = filter_candidates(
        profiles, ROLE_TASKS,
        current_workload=None, total_workdays=10, skill_role_map=ROLE_MAP,
    )
    assert len(result) == 7


def test_role_cap_picks_top_five_by_skill_level_when_capacity_is_enough():
    # 7명 모두 여유 있음(총 10평일 중 아무도 안 씀) -> 숙련도 상위 5명만 남는다.
    profiles = [
        _profile(employee_id=f"EMP-{i}", skills=["Django"], skill_levels={"Django": i})
        for i in range(1, 8)  # 숙련도 1~7
    ]
    result = filter_candidates(
        profiles, ROLE_TASKS,
        current_workload={}, total_workdays=10, skill_role_map=ROLE_MAP,
    )
    assert len(result) == 5
    assert {p.employee_id for p in result} == {"EMP-3", "EMP-4", "EMP-5", "EMP-6", "EMP-7"}


def test_role_cap_expands_when_top_five_lack_capacity():
    # 숙련도 상위 5명(EMP-3~7)은 이미 꽉 참(부하 크게 줌) -> 남는 가용일수 0.
    # 하위 2명(EMP-1, EMP-2)은 여유 있어 필요분을 못 채우면 추가로 끌려온다.
    profiles = [
        _profile(employee_id=f"EMP-{i}", skills=["Django"], skill_levels={"Django": i})
        for i in range(1, 8)
    ]
    heavy_workload = {f"EMP-{i}": 1000.0 for i in range(3, 8)}  # 상위 5명 전부 과부하
    result = filter_candidates(
        profiles, ROLE_TASKS,
        current_workload=heavy_workload, total_workdays=10, skill_role_map=ROLE_MAP,
    )
    ids = {p.employee_id for p in result}
    # 상위 5명은 그대로 유지하고(캡은 순위로 고정), 가용시간 부족분을 메우려
    # 하위 순위(EMP-2, 여유 있음)가 최소 하나는 추가돼야 한다.
    assert {"EMP-3", "EMP-4", "EMP-5", "EMP-6", "EMP-7"} <= ids
    assert "EMP-2" in ids
    assert len(ids) > 5


def test_role_cap_breaks_hour_ties_by_role_name_deterministically():
    # 2026-09-15: BACKEND/DATA_ENGINEER가 필요 시간(24h -> 5평일)이 정확히 동점이면,
    # roles_needed가 set이라 처리 순서가 프로세스마다 랜덤해질 수 있었다(remaining_pool
    # 공유 소진 순서가 그 순서에 달려있음). role 이름을 2차 정렬키로 넣어 "BACKEND"가
    # "DATA_ENGINEER"보다 알파벳상 먼저 오게 고정했다 — 그래서 EMP-SHARED의 가용일수는
    # 항상 BACKEND가 먼저 가져가고, DATA_ENGINEER 쪽이 부족분을 메우려 확장돼야 한다.
    two_role_map = {"Django": {"BACKEND": 1.0}, "MySQL": {"DATA_ENGINEER": 1.0}}
    tasks = [
        {
            "task_id": "T-BACKEND",
            "title": "t",
            "description": "d",
            "source_req_id": "FR-01-001",
            "required_skills": ["Django"],
            "estimated_hours": 24,  # plan_days(24, 1.2) = 5평일 — DATA_ENGINEER와 동점
        },
        {
            "task_id": "T-DATA",
            "title": "t",
            "description": "d",
            "source_req_id": "FR-01-002",
            "required_skills": ["MySQL"],
            "estimated_hours": 24,  # plan_days(24, 1.2) = 5평일 — BACKEND와 동점
        },
    ]

    shared = _profile(
        employee_id="EMP-SHARED", skills=["Django", "MySQL"],
        skill_levels={"Django": 5, "MySQL": 5},
    )
    backend_only = [
        _profile(employee_id=f"EMP-B{i}", skills=["Django"], skill_levels={"Django": 4})
        for i in range(1, 5)
    ]
    data_weak = [
        _profile(employee_id=f"EMP-D{i}", skills=["MySQL"], skill_levels={"MySQL": 2})
        for i in range(1, 6)
    ]
    data_backup = _profile(employee_id="EMP-D6", skills=["MySQL"], skill_levels={"MySQL": 1})

    profiles = [shared] + backend_only + data_weak + [data_backup]
    current_workload = {
        **{f"EMP-D{i}": 241.0 for i in range(1, 6)},  # 남는 가용일수 1평일
        "EMP-D6": 196.0,  # 남는 가용일수 10평일(숙련도 최하라 후순위)
    }

    result = filter_candidates(
        profiles, tasks,
        current_workload=current_workload, total_workdays=50, skill_role_map=two_role_map,
    )
    ids = {p.employee_id for p in result}

    # BACKEND가 먼저 처리돼 EMP-SHARED의 가용일수를 가져가므로, DATA_ENGINEER는
    # D1~D4(4평일)만으로 부족해 D5까지 확장돼야 한다 — D6은 여전히 불필요.
    assert "EMP-D5" in ids
    assert "EMP-D6" not in ids


def test_role_cap_does_not_double_count_shared_candidate_across_roles():
    # 2026-09-14: Django+MySQL을 둘 다 가진 EMP-SHARED가 BACKEND/DATA_ENGINEER
    # 양쪽 후보에 다 잡힌다. 고치기 전엔 EMP-SHARED의 남는 가용일수(50평일, 풀로
    # 비어있음)가 두 역할 모두에서 독립적으로 카운트돼, DATA_ENGINEER 쪽 필요
    # 5평일이 이미 채워진 것처럼 보여 확장이 안 일어났다. 고친 뒤에는 BACKEND
    # 처리 때 EMP-SHARED의 가용일수가 소진 처리되어, DATA_ENGINEER 계산에선
    # 0으로 잡히고 — 그래서 실제로 5순위 후보(EMP-D5)까지 끌어와야 한다.
    two_role_map = {"Django": {"BACKEND": 1.0}, "MySQL": {"DATA_ENGINEER": 1.0}}
    tasks = [
        {
            "task_id": "T-BACKEND",
            "title": "t",
            "description": "d",
            "source_req_id": "FR-01-001",
            "required_skills": ["Django"],
            "estimated_hours": 200,  # plan_days(200, 1.2) = 40평일 필요
        },
        {
            "task_id": "T-DATA",
            "title": "t",
            "description": "d",
            "source_req_id": "FR-01-002",
            "required_skills": ["MySQL"],
            "estimated_hours": 24,  # plan_days(24, 1.2) = 5평일 필요
        },
    ]

    shared = _profile(
        employee_id="EMP-SHARED", skills=["Django", "MySQL"],
        skill_levels={"Django": 5, "MySQL": 5},
    )
    # BACKEND 전용 4명 — EMP-SHARED와 합쳐 정확히 5명(상한)이라 확장이 필요 없다.
    backend_only = [
        _profile(employee_id=f"EMP-B{i}", skills=["Django"], skill_levels={"Django": 4})
        for i in range(1, 5)
    ]
    # DATA_ENGINEER 후보는 EMP-SHARED 포함 7명 — 상한(5)을 넘겨 확장 여부가
    # 실제로 갈린다. D1~D5는 거의 꽉 차 있고(남는 1평일), D6은 여유 있지만
    # 숙련도가 가장 낮아 순위 밖.
    data_weak = [
        _profile(employee_id=f"EMP-D{i}", skills=["MySQL"], skill_levels={"MySQL": 2})
        for i in range(1, 6)
    ]
    data_backup = _profile(employee_id="EMP-D6", skills=["MySQL"], skill_levels={"MySQL": 1})

    profiles = [shared] + backend_only + data_weak + [data_backup]
    current_workload = {
        # D1~D5: 50평일 중 49평일을 이미 씀 -> 남는 가용일수 1평일.
        **{f"EMP-D{i}": 241.0 for i in range(1, 6)},
        # D6: 40평일을 씀 -> 남는 가용일수 10평일(그래도 숙련도가 낮아 후순위).
        "EMP-D6": 196.0,
        # EMP-SHARED/B1~B4는 이 프로젝트 전에는 부하가 없음(남는 가용일수 50평일).
    }

    result = filter_candidates(
        profiles, tasks,
        current_workload=current_workload, total_workdays=50, skill_role_map=two_role_map,
    )
    ids = {p.employee_id for p in result}

    assert "EMP-D5" in ids  # 중복 계산 버그가 남아있었다면 여기서 빠졌을 후보
    assert "EMP-D6" not in ids  # 채워야 할 5평일이 D5까지로 이미 충족되므로 불필요
    assert ids == {"EMP-SHARED", "EMP-B1", "EMP-B2", "EMP-B3", "EMP-B4", "EMP-D1", "EMP-D2", "EMP-D3", "EMP-D4", "EMP-D5"}


def test_role_cap_leaves_unmapped_skill_candidates_uncapped():
    # skill_role_map에 없는 스킬(팀에 그 역량 가진 사람 자체가 드묾)은 역할로 못 묶어
    # 상한 없이 전부 통과한다.
    tasks = [
        {
            "task_id": "T1",
            "title": "t",
            "description": "d",
            "source_req_id": "FR-01-001",
            "required_skills": ["희귀스킬"],
            "estimated_hours": 8,
        }
    ]
    profiles = [_profile(employee_id=f"EMP-{i}", skills=["희귀스킬"]) for i in range(7)]
    result = filter_candidates(
        profiles, tasks,
        current_workload={}, total_workdays=10, skill_role_map={},
    )
    assert len(result) == 7

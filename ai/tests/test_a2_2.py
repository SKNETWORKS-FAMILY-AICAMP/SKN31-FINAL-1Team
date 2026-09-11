"""
tests/test_a2_2.py

2026-09-11 (Phase 2): 업무 생성이 채우는 일정 입력 필드 검증.
  - _renumber() 가 dependency_task_ids 를 새 task_id 로 다시 매기는지
  - flatten_assignable_units() 가 Task 단위 의존성을 unit 단위로 펴는지
LLM 을 쓰지 않으므로 전부 결정적으로 확인한다.
"""

from assignee_recommend.rule_filter import flatten_assignable_units
from task_generation.agent import _renumber
from task_generation.schemas import SubTask, TaskItem


def _task(task_id, *, epic="E1", deps=None, subs=None, buffer=None, feature=None, hours=4.0):
    return TaskItem(
        task_id=task_id,
        epic_id=epic,
        epic_title="epic",
        title=task_id,
        description="d",
        required_skills=["Django"],
        estimated_hours=hours,
        dependency_task_ids=deps or [],
        risk_buffer_factor=buffer,
        feature_area=feature,
        difficulty="중",
        difficulty_reason="r",
        source_req_id="FR-01-001",
        subtasks=subs or [],
    )


# ---------------------------------------------------------------------------
# _renumber: 의존성 remap
# ---------------------------------------------------------------------------
def test_renumber_remaps_dependency_ids_within_group():
    group = [_task("TASK-005"), _task("TASK-009", deps=["TASK-005"])]
    result = _renumber([group])
    assert [t.task_id for t in result] == ["TASK-001", "TASK-002"]
    assert result[1].dependency_task_ids == ["TASK-001"]


def test_renumber_handles_forward_reference():
    # 의존 대상이 리스트에서 뒤에 있어도(전방 참조) 매핑된다
    group = [_task("TASK-B", deps=["TASK-A"]), _task("TASK-A")]
    result = _renumber([group])
    by_title = {t.title: t for t in result}
    assert by_title["TASK-B"].dependency_task_ids == [by_title["TASK-A"].task_id]


def test_renumber_drops_dangling_and_cross_group_refs():
    g1 = [_task("TASK-001")]
    g2 = [_task("TASK-001", deps=["TASK-001", "GHOST"])]  # 다른 그룹의 우연한 동일 ID + 없는 ID
    result = _renumber([g1, g2])
    assert result[1].dependency_task_ids == []  # 그룹 밖/없는 참조는 버림


def test_renumber_drops_self_reference():
    group = [_task("TASK-007", deps=["TASK-007"])]
    result = _renumber([group])
    assert result[0].dependency_task_ids == []


# ---------------------------------------------------------------------------
# flatten_assignable_units: Task 의존성 -> unit 의존성
# ---------------------------------------------------------------------------
def test_task_dependency_becomes_unit_dependency():
    tasks = [t.model_dump(mode="json") for t in [
        _task("TASK-001"),
        _task("TASK-002", deps=["TASK-001"]),
    ]]
    units = {u["unit_id"]: u for u in flatten_assignable_units(tasks)}
    assert units["TASK-002"]["depends_on"] == ["TASK-001"]
    assert units["TASK-001"]["depends_on"] == []


def test_dependency_on_task_with_subtasks_expands_to_all_subtask_units():
    subs = [
        SubTask(subtask_id="SUBTASK-001-1", title="s1", description="d", estimated_hours=2),
        SubTask(subtask_id="SUBTASK-001-2", title="s2", description="d", estimated_hours=2),
    ]
    tasks = [t.model_dump(mode="json") for t in [
        _task("TASK-001", subs=subs),
        _task("TASK-002", deps=["TASK-001"]),
    ]]
    units = {u["unit_id"]: u for u in flatten_assignable_units(tasks)}
    assert units["TASK-002"]["depends_on"] == ["SUBTASK-001-1", "SUBTASK-001-2"]


def test_subtasks_inherit_parent_deps_buffer_and_feature():
    subs = [SubTask(subtask_id="SUBTASK-002-1", title="s", description="d", estimated_hours=3)]
    tasks = [t.model_dump(mode="json") for t in [
        _task("TASK-001"),
        _task("TASK-002", deps=["TASK-001"], subs=subs, buffer=1.5, feature="주문"),
    ]]
    units = {u["unit_id"]: u for u in flatten_assignable_units(tasks)}
    sub_unit = units["SUBTASK-002-1"]
    assert sub_unit["depends_on"] == ["TASK-001"]
    assert sub_unit["risk_buffer_factor"] == 1.5
    assert sub_unit["feature_area"] == "주문"


def test_missing_new_fields_default_safely():
    # Phase 1 이전 형태(새 필드 없음)의 dict 도 그대로 처리돼야 한다
    legacy = {
        "task_id": "TASK-001", "title": "t", "description": "d",
        "required_skills": [], "estimated_hours": 4.0,
        "source_req_id": "FR-01-001", "subtasks": [],
    }
    units = flatten_assignable_units([legacy])
    assert units[0]["depends_on"] == []
    assert units[0]["risk_buffer_factor"] is None

"""
tests/manual_verify_batch_recommend.py

assignee_recommend_node의 배치화(LLM 호출 N회 -> 최대 2회)가 외부 계약(반환
shape)을 그대로 유지하는지, create_structured를 mock으로 대체해 실제 API
호출 없이 확인하는 스크립트.

실행:
  cd ai
  python3 tests/manual_verify_batch_recommend.py
"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assignee_recommend import agent as agent_module
from assignee_recommend.schemas import (
    BatchHoldExplanations,
    BatchHoldItem,
    BatchRecommendationReasons,
    BatchReasonItem,
    HoldExplanation,
    RecommendationReason,
)

call_log = []


def fake_create_structured(*, system_prompt, user_message, response_model, **kwargs):
    call_log.append(response_model.__name__)
    if response_model is BatchRecommendationReasons:
        # system_prompt 안에 넣은 unit_id들을 그대로 다시 뽑아 매핑해준다.
        import re

        unit_ids = re.findall(r'"unit_id":\s*"([^"]+)"', system_prompt)
        unit_ids = list(dict.fromkeys(unit_ids))  # unit 쪽 unit_id만(중복 없이, 순서 유지)
        return BatchRecommendationReasons(
            results=[
                BatchReasonItem(
                    unit_id=uid,
                    reason=RecommendationReason(
                        skill_fit=f"[mock] {uid} skill_fit",
                        workload=f"[mock] {uid} workload",
                        similar_experience=f"[mock] {uid} similar_experience",
                    ),
                )
                for uid in unit_ids
            ]
        )
    if response_model is BatchHoldExplanations:
        import re

        unit_ids = re.findall(r'"unit_id":\s*"([^"]+)"', system_prompt)
        unit_ids = list(dict.fromkeys(unit_ids))
        return BatchHoldExplanations(
            results=[
                BatchHoldItem(unit_id=uid, explanation=f"[mock] {uid} 보류 사유")
                for uid in unit_ids
            ]
        )
    if response_model is RecommendationReason:
        return RecommendationReason(
            skill_fit="[fallback] skill_fit",
            workload="[fallback] workload",
            similar_experience="[fallback] similar_experience",
        )
    if response_model is HoldExplanation:
        return HoldExplanation(explanation="[fallback] 보류 사유")
    raise AssertionError(f"unexpected response_model: {response_model}")


def make_state(tasks, members, workload):
    return {
        "member_profiles": members,
        "current_workload": workload,
        "project_start_date": "2026-09-01",
        "project_end_date": "2026-09-30",
        "tasks": tasks,
        "requirement_doc": {"requirements": [{"id": "REQ-001", "priority": "HIGH"}]},
    }


def build_tasks(n, required_skills):
    """n개의 독립 Task(서브태스크 없음)를 만든다 — 각각 assignable unit 1개씩."""
    return [
        {
            "task_id": f"TASK-{i:03d}",
            "title": f"업무 {i}",
            "description": f"업무 {i} 설명",
            "required_skills": required_skills,
            "estimated_hours": 4.0,
            "source_req_id": "REQ-001",
        }
        for i in range(1, n + 1)
    ]


def test_held_units_all_get_hold_explanation():
    """후보가 없는 unit들 -> 모두 hold_explanation 채워지고 review_required=True."""
    call_log.clear()
    tasks = build_tasks(5, required_skills=["존재하지않는스킬"])
    members = [
        {"employee_id": "EMP-001", "skills": ["Django"], "past_similar_tasks": [], "certifications": []},
    ]
    state = make_state(tasks, members, workload={})

    with patch.object(agent_module, "create_structured", side_effect=fake_create_structured):
        result = agent_module.assignee_recommend_node(state)

    assert result["error"] is None, result
    assignments = result["assignments"]
    assert len(assignments) == 5
    for a in assignments:
        assert a["employee_id"] is None
        assert a["review_required"] is True
        assert a["hold_explanation"] is not None and "[mock]" in a["hold_explanation"]
        assert a["reason"] is None

    # 5개 unit 전부 보류 -> BatchHoldExplanations 1회 호출로 처리됐어야 한다
    # (5 <= BATCH_CHUNK_SIZE=10 이므로 청크 1개).
    assert call_log == ["BatchHoldExplanations"], call_log
    print("test_held_units_all_get_hold_explanation: PASS (LLM calls =", len(call_log), ")")


def test_assigned_units_get_reason_with_same_fields():
    """배정 가능한 unit들 -> reason에 skill_fit/workload/similar_experience 채워지고 review_required=False."""
    call_log.clear()
    tasks = build_tasks(4, required_skills=["Django"])
    members = [
        {
            "employee_id": "EMP-001",
            "skills": ["Django", "REST API"],
            "past_similar_tasks": ["p1", "p2"],
            "certifications": [],
        },
        {
            "employee_id": "EMP-002",
            "skills": ["Django"],
            "past_similar_tasks": [],
            "certifications": [],
        },
    ]
    state = make_state(tasks, members, workload={})

    with patch.object(agent_module, "create_structured", side_effect=fake_create_structured):
        result = agent_module.assignee_recommend_node(state)

    assert result["error"] is None, result
    assignments = result["assignments"]
    assert len(assignments) == 4
    for a in assignments:
        assert a["employee_id"] is not None
        assert a["review_required"] is False
        assert a["hold_explanation"] is None
        reason = a["reason"]
        assert reason is not None
        assert set(reason.keys()) == {"skill_fit", "workload", "similar_experience"}
        assert "[mock]" in reason["skill_fit"]

    assert call_log == ["BatchRecommendationReasons"], call_log
    print("test_assigned_units_get_reason_with_same_fields: PASS (LLM calls =", len(call_log), ")")


def test_mixed_batch_uses_at_most_two_calls():
    """배정 그룹 + 보류 그룹이 섞여 있어도 총 LLM 호출은 최대 2회(그룹당 1회, 청크 크기 이내)."""
    call_log.clear()
    assigned_tasks = build_tasks(6, required_skills=["Django"])
    held_tasks = [
        {
            "task_id": f"TASK-HELD-{i:03d}",
            "title": f"보류 업무 {i}",
            "description": "설명",
            "required_skills": ["존재하지않는스킬"],
            "estimated_hours": 4.0,
            "source_req_id": "REQ-001",
        }
        for i in range(1, 4)
    ]
    tasks = assigned_tasks + held_tasks
    members = [
        {"employee_id": "EMP-001", "skills": ["Django"], "past_similar_tasks": [], "certifications": []},
    ]
    state = make_state(tasks, members, workload={})

    with patch.object(agent_module, "create_structured", side_effect=fake_create_structured):
        result = agent_module.assignee_recommend_node(state)

    assert result["error"] is None, result
    assignments = result["assignments"]
    assert len(assignments) == 9
    assert len(call_log) <= 2, call_log
    assert set(call_log) <= {"BatchRecommendationReasons", "BatchHoldExplanations"}
    print("test_mixed_batch_uses_at_most_two_calls: PASS (LLM calls =", len(call_log), "->", call_log, ")")


def test_missing_unit_id_falls_back_to_single_call():
    """배치 응답에서 unit_id 하나가 누락되면 단건 호출로 보완되는지 확인."""
    call_log.clear()
    tasks = build_tasks(3, required_skills=["Django"])
    members = [
        {"employee_id": "EMP-001", "skills": ["Django"], "past_similar_tasks": [], "certifications": []},
    ]
    state = make_state(tasks, members, workload={})

    def flaky_create_structured(*, system_prompt, user_message, response_model, **kwargs):
        if response_model is BatchRecommendationReasons:
            call_log.append("BatchRecommendationReasons")
            # TASK-002를 일부러 빠뜨린다.
            return BatchRecommendationReasons(
                results=[
                    BatchReasonItem(
                        unit_id="TASK-001",
                        reason=RecommendationReason(
                            skill_fit="a", workload="b", similar_experience="c"
                        ),
                    ),
                    BatchReasonItem(
                        unit_id="TASK-003",
                        reason=RecommendationReason(
                            skill_fit="a", workload="b", similar_experience="c"
                        ),
                    ),
                ]
            )
        if response_model is RecommendationReason:
            call_log.append("RecommendationReason(fallback)")
            return RecommendationReason(
                skill_fit="[fallback]", workload="[fallback]", similar_experience="[fallback]"
            )
        raise AssertionError(f"unexpected response_model: {response_model}")

    with patch.object(agent_module, "create_structured", side_effect=flaky_create_structured):
        result = agent_module.assignee_recommend_node(state)

    assert result["error"] is None, result
    by_id = {a["unit_id"]: a for a in result["assignments"]}
    assert by_id["TASK-002"]["reason"]["skill_fit"] == "[fallback]"
    assert call_log == ["BatchRecommendationReasons", "RecommendationReason(fallback)"], call_log
    print("test_missing_unit_id_falls_back_to_single_call: PASS (calls =", call_log, ")")


if __name__ == "__main__":
    test_held_units_all_get_hold_explanation()
    test_assigned_units_get_reason_with_same_fields()
    test_mixed_batch_uses_at_most_two_calls()
    test_missing_unit_id_falls_back_to_single_call()
    print("\nALL TESTS PASSED")

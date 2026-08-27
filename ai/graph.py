"""
graph.py

Track A(문서 생성 파이프라인) 전체를 하나의 LangGraph로 조립한다.
개별 에이전트 로직(각 노드가 "무엇을 하는지")은 각 에이전트 폴더의
agent.py에 있고, 이 파일은 "누가 누구 다음에 오는지 / 반려되면
어디로 되돌아가는지"만 담당한다.

담당자 구분 없이, 파이프라인 순서 기준으로 배치했다:
  A1-1 -> A1-2 -> [기획서 검토] -> A2-1 -> [요구사항정의서 검토] -> A2-2 -> A2-3
"""

from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

import shared.django_bootstrap  # noqa: F401  (Django 초기화 부작용 — backend 모델 import 전에 실행되어야 함)
from meeting_analysis.agent import meeting_analysis_node
from plan_draft.agent import plan_draft_node
from plan_draft.review_sync import apply_plan_review_decision
from requirement_draft.agent import requirement_draft_node
from task_generation.agent import task_generation_node
from assignee_recommend.agent import assignee_recommend_node
from state import PipelineState


# ---------------------------------------------------------------------------
# 사람 검토(human-in-the-loop) 게이트
# ---------------------------------------------------------------------------

def plan_review_gate(state: PipelineState) -> dict:
    """A1-2가 만든 기획서를 PM이 승인/반려할 때까지 여기서 멈춘다.

    interrupt()가 재개될 때 넘어오는 decision 형태:
      승인: {"action": "승인", "reviewer_id": "<승인자 UUID>"}
      반려: {"action": "반려", "reason": "<반려 사유>"}
    """
    decision = interrupt({"plan": state["plan"], "question": "기획서 승인 또는 반려?"})

    apply_plan_review_decision(
        plan_id=state["plan_id"],
        decision=decision["action"],
        reviewer_id=decision.get("reviewer_id"),
        reject_reason=decision.get("reason"),
    )

    if decision["action"] == "반려":
        return {"plan_rejection_reason": decision.get("reason")}
    return {"plan_rejection_reason": None}


def requirement_review_gate(state: PipelineState) -> dict:
    """A2-1이 만든 요구사항정의서를 PM이 승인/반려할 때까지 여기서 멈춘다."""
    decision = interrupt(
        {"requirement_doc": state["requirement_doc"], "question": "요구사항정의서 승인 또는 반려?"}
    )
    if decision["action"] == "반려":
        return {"requirement_rejection_reason": decision.get("reason")}
    return {"requirement_rejection_reason": None}


def route_after_plan_review(state: PipelineState) -> str:
    if state.get("plan_rejection_reason"):
        return "a1_2_plan_draft"          # 반려 -> A1-2로 되돌아감
    return "a2_1_requirement_draft"       # 승인 -> 다음 단계


def route_after_requirement_review(state: PipelineState) -> str:
    if state.get("requirement_rejection_reason"):
        return "a2_1_requirement_draft"   # 반려 -> A2-1로 되돌아감
    return "a2_2_task_generation"         # 승인 -> 다음 단계


# ---------------------------------------------------------------------------
# 그래프 조립
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    graph = StateGraph(PipelineState)

    graph.add_node("a1_1_meeting_analysis", meeting_analysis_node)
    graph.add_node("a1_2_plan_draft", plan_draft_node)
    graph.add_node("plan_review_gate", plan_review_gate)
    graph.add_node("a2_1_requirement_draft", requirement_draft_node)
    graph.add_node("requirement_review_gate", requirement_review_gate)
    graph.add_node("a2_2_task_generation", task_generation_node)
    graph.add_node("a2_3_assignee_recommend", assignee_recommend_node)

    graph.set_entry_point("a1_1_meeting_analysis")
    graph.add_edge("a1_1_meeting_analysis", "a1_2_plan_draft")
    graph.add_edge("a1_2_plan_draft", "plan_review_gate")
    graph.add_conditional_edges(
        "plan_review_gate",
        route_after_plan_review,
        {"a1_2_plan_draft": "a1_2_plan_draft", "a2_1_requirement_draft": "a2_1_requirement_draft"},
    )
    graph.add_edge("a2_1_requirement_draft", "requirement_review_gate")
    graph.add_conditional_edges(
        "requirement_review_gate",
        route_after_requirement_review,
        {
            "a2_1_requirement_draft": "a2_1_requirement_draft",
            "a2_2_task_generation": "a2_2_task_generation",
        },
    )
    graph.add_edge("a2_2_task_generation", "a2_3_assignee_recommend")
    graph.add_edge("a2_3_assignee_recommend", END)

    return graph


# 실행 시:
#   from langgraph.checkpoint.redis import RedisSaver   # 팀 인프라에 맞는 checkpointer로 교체
#   app = build_graph().compile(checkpointer=RedisSaver(...))
#   app.invoke({"meeting_id": "MTG-2026-08-25-01"})

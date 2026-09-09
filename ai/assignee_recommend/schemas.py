"""
a2_3_assignee_recommend/schemas.py

컨텍스트 설계 요약
  - 입력: 업무 목록(A2-2 출력 전체) + 팀원 이력·기술·총 가용시간 — SQL 조회
  - 방식: 하이브리드 — "누구에게 배정할지"는 그리디 스케줄러(코드)가 우선순위·
          가용시간 기준으로 전부 확정한다. LLM은 그 결과에 대한 근거 문장
          (또는 후보가 없어 보류된 이유)만 생성한다 (agent.py, rule_filter.py 참고).
  - Tools: 없음
  - 출력: 업무 단위(Task 또는 Subtask)별 확정 배정 + 근거, 또는 보류 + 사유
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class RecommendationReason(BaseModel):
    """LLM이 생성하는, 이미 확정된 담당자에 대한 근거 문장 3종."""

    skill_fit: str
    workload: str
    similar_experience: str


class HoldExplanation(BaseModel):
    """LLM이 생성하는, 배정 보류 사유 설명."""

    explanation: str


class ReasonBatchItem(BaseModel):
    """배치 근거 생성 결과 1건 — unit_id로 원본 업무와 매칭한다."""

    unit_id: str
    skill_fit: str
    workload: str
    similar_experience: str


class ReasonBatch(BaseModel):
    """
    여러 업무의 근거 문장을 한 번의 LLM 호출로 생성한 결과(agent.py의
    generate_reasons_batch 참고). 입력받은 unit_id 전부가 items에 빠짐없이
    있어야 하며, 누락되면 호출부가 단건으로 보완 호출한다.
    """

    items: List[ReasonBatchItem] = Field(default_factory=list)


class HoldBatchItem(BaseModel):
    """배치 보류 사유 생성 결과 1건 — unit_id로 원본 업무와 매칭한다."""

    unit_id: str
    explanation: str


class HoldBatch(BaseModel):
    """여러 업무의 보류 사유를 한 번의 LLM 호출로 생성한 결과."""

    items: List[HoldBatchItem] = Field(default_factory=list)


class AssignmentResult(BaseModel):
    """
    배정 단위(Task 또는 Subtask) 1건에 대한 최종 결과.
    employee_id/score는 스케줄러(코드)가 확정한 값이고, reason/hold_explanation만
    LLM이 채운 텍스트다. LLM이 employee_id나 score를 재판단하지 않는다.
    """

    unit_id: str = Field(..., description="TASK-{순번} 또는 SUBTASK-{순번}-{하위순번}")
    parent_task_id: Optional[str] = Field(None, description="Subtask인 경우 소속 Task ID")
    source_req_id: str

    employee_id: Optional[str] = None
    score: Optional[float] = None
    reason: Optional[RecommendationReason] = None

    review_required: bool = False
    hold_explanation: Optional[str] = None


class AssignmentBatch(BaseModel):
    results: List[AssignmentResult] = Field(default_factory=list)

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


# --- 배치 LLM 호출용 스키마 (2026-09, OpenAI TPM 레이트리밋 대응) ---
#
# 기존엔 확정 배정 단위(unit)마다 LLM을 한 번씩 호출해 RecommendationReason/
# HoldExplanation을 받았다 — unit이 10~20개면 호출도 10~20번이라 OpenAI TPM
# 한도(30,000 tokens/min)에 자주 걸렸다. 아래 두 스키마는 여러 unit을 한
# 요청에 묶어 응답받기 위한 것으로, 기존 RecommendationReason/HoldExplanation
# 자체는 그대로 두고(다른 코드/스키마가 그대로 참조하므로) unit_id로 매핑되는
# 배치 래퍼만 추가한다.


class BatchReasonItem(BaseModel):
    """배치 응답 안에서 각 unit에 대한 근거 문장 1건."""

    unit_id: str = Field(..., description="입력으로 준 [업무 목록]의 unit_id와 정확히 일치해야 함")
    reason: RecommendationReason


class BatchRecommendationReasons(BaseModel):
    """여러 unit에 대한 근거 문장을 한 번에 받기 위한 배치 응답."""

    results: List[BatchReasonItem] = Field(default_factory=list)


class BatchHoldItem(BaseModel):
    """배치 응답 안에서 각 unit에 대한 보류 사유 설명 1건."""

    unit_id: str = Field(..., description="입력으로 준 [업무 목록]의 unit_id와 정확히 일치해야 함")
    explanation: str


class BatchHoldExplanations(BaseModel):
    """여러 unit에 대한 보류 사유를 한 번에 받기 위한 배치 응답."""

    results: List[BatchHoldItem] = Field(default_factory=list)

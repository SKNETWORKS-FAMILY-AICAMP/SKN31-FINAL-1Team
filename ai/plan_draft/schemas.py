"""
a1_2_plan_draft/schemas.py

컨텍스트 설계 요약
  - 입력: A1-1 출력(구조화 JSON), State Passing
  - 정적 참고자료: "goal은 한 문장, requirements는 decisions/action_items에서 파생" 지침 + few-shot
  - Tools: 없음
  - 출력: 기획서 JSON
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class PlanRequirement(BaseModel):
    req_id: str
    content: str


class PlanDocument(BaseModel):
    """A1-2 출력 — 다음 노드(A2-1)의 입력으로 State Passing된다."""

    project_id: str
    meeting_id: Optional[str] = None
    title: str
    goal: str = Field(..., description="한 문장으로 서술")
    requirements: List[PlanRequirement] = Field(..., min_length=1)
    pipeline_stage: str = "기획서_검토대기"

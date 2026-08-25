"""
a1_1_meeting_analysis/schemas.py

컨텍스트 설계 요약
  - 입력: 회의록 원문 텍스트 (meeting_log 테이블 또는 S3 원문)
  - 정적 참고자료: 구조화 인스트럭션 + few-shot 2~3건
  - Tools: 없음
  - 출력: 구조화 JSON (topic/decisions/action_items)
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class ActionItem(BaseModel):
    owner: Optional[str] = Field(None, description="회의록에서 담당자가 명시된 경우만 채움")
    task: str
    due: Optional[str] = Field(None, description="YYYY-MM-DD, 명시 안 됐으면 null")


class MeetingAnalysis(BaseModel):
    """A1-1 출력 — 다음 노드(A1-2)의 입력으로 State Passing된다."""

    topic: str = Field(..., description="회의 주제 한 줄 요약")
    decisions: List[str] = Field(..., description="결정된 사항 목록")
    action_items: List[ActionItem] = Field(default_factory=list)

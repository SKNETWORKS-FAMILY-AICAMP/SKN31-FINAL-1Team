"""
a2_2_task_generation/schemas.py

컨텍스트 설계 요약
  - 입력: A2-1 출력(요구사항정의서 JSON), State Passing
  - 정적 참고자료: 업무유형 6종 + Depth 기준(Epic->Task) + 3원칙, Prompt Template + Few-shot
  - 동적 조회: 프로젝트 참여인원 수 — SQL 조회 (FR-05-014: 업무 개수는 참여인원 이상 7개 이하)
  - Tools: 없음
  - 출력: 업무 리스트 JSON (3개 이상 7개 이하)
"""

from typing import List

from pydantic import BaseModel, Field, field_validator


class TaskItem(BaseModel):
    task_id: str
    title: str
    description: str
    task_type: str = Field(..., description="task_type 테이블의 6종 중 하나")
    estimated_hours: float
    difficulty: str = Field(..., description="상/중/하")
    difficulty_reason: str = Field(..., description="난이도 판단 근거 — 화면에 그대로 노출")
    source_req_id: str = Field(..., description="어느 요구사항에서 파생됐는지 추적용")


class TaskList(BaseModel):
    tasks: List[TaskItem] = Field(..., min_length=3, max_length=7)

    @field_validator("tasks")
    @classmethod
    def validate_min_count_vs_participants(cls, v: List[TaskItem]) -> List[TaskItem]:
        # 참여인원 수 기반 최소 개수 검증은 참여인원 수를 아는 노드(agent.py)에서
        # 별도로 재검증한다 — 이 스키마 자체는 3~7 범위만 보장한다.
        return v

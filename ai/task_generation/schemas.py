"""
task_generation/schemas.py

컨텍스트 설계 요약
  - 입력: 요구사항정의서 출력(요구사항정의서 JSON), State Passing
  - 정적 참고자료: 업무유형 6종 + Depth 기준(Epic->Task->Subtask) + 3원칙, Prompt Template + Few-shot
  - 동적 조회: 프로젝트 참여인원 수의 SQL 조회 (FR-05-014: 업무 개수는 참여인원 이상 7개 이하)
  - Tools: 없음
  - 출력: 업무 리스트 JSON (Epic 정보 포함, Subtask 중첩)
"""

from typing import List

from pydantic import BaseModel, Field, field_validator


class SubTask(BaseModel):
    subtask_id: str = Field(..., description="SUBTASK-{task순번}-{하위순번} 형식 (예: SUBTASK-001-1)")
    title: str
    description: str
    estimated_hours: float


class TaskItem(BaseModel):
    task_id: str = Field(..., description="TASK-{순번} 형식 (예: TASK-001)")
    epic_id: str = Field(..., description="소속 Epic 식별자 (EPIC-{순번} 형식, 예: EPIC-001)")
    epic_title: str = Field(..., description="소속 Epic 명")
    title: str
    description: str
    task_type: str = Field(..., description="task_type 테이블의 6종 중 하나")
    estimated_hours: float
    difficulty: str = Field(..., description="상/중/하")
    difficulty_reason: str = Field(..., description="난이도 판단 근거 — 화면에 그대로 노출")
    source_req_id: str = Field(..., description="어느 요구사항에서 파생됐는지 추적용")
    subtasks: List[SubTask] = Field(
        default_factory=list,
        max_length=5,
        description="decomposition_principles 3원칙 미충족 시에만 생성. 충족 시 빈 리스트.",
    )


class TaskList(BaseModel):
    tasks: List[TaskItem] = Field(..., min_length=3, max_length=7)

    @field_validator("tasks")
    @classmethod
    def validate_min_count_vs_participants(cls, v: List[TaskItem]) -> List[TaskItem]:
        return v

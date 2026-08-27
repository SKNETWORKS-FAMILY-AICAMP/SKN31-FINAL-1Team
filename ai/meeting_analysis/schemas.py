"""
노드 ① 회의록 구조화 스키마.

여기가 이 노드의 계약서입니다.
프롬프트도, 검증도, 하류 노드도 전부 이 파일을 기준으로 움직입니다.

## 모델이 두 개인 이유

MeetingExtraction : LLM이 생성하는 부분만
MeetingStructured : 위 + 파이프라인이 채우는 필드

Instructor에 response_model로 넘기는 건 MeetingExtraction입니다.
validation_notes 같은 시스템 필드를 LLM 스키마에 넣으면
모델이 "이것도 채워야 하나?" 하고 뭔가 써넣습니다.
아예 보여주지 않는 게 안전합니다.
"""

from typing import Optional

from pydantic import BaseModel, Field

from shared.schemas_base import Evidence, Priority
from enum import Enum


class DecisionCategory(str, Enum):
    FEATURE = "feature"
    TECH = "tech"
    SCOPE = "scope"


class Project(BaseModel):
    name: str = Field(..., description="프로젝트명")
    background: str = Field(..., description="프로젝트 배경")
    problem: str = Field(..., description="해결하려는 문제")
    goals: list[str] = Field(..., min_length=1, description="프로젝트 목표")
    evidence: Evidence


class UserGroup(BaseModel):
    type: str = Field(..., description="사용자 유형 (예: 서기, PM)")
    description: str
    needs: list[str] = Field(default_factory=list, description="이 사용자의 요구")
    evidence: Evidence


class RequirementItem(BaseModel):
    content: str
    priority: Priority = Priority.MEDIUM
    evidence: Evidence


class Requirements(BaseModel):
    functional: list[RequirementItem] = Field(
        default_factory=list, description="기능 요구사항"
    )
    non_functional: list[RequirementItem] = Field(
        default_factory=list, description="성능·보안·사용성 요구사항"
    )
    data: list[RequirementItem] = Field(
        default_factory=list, description="저장·연동 데이터 요구사항"
    )
    technical: list[RequirementItem] = Field(
        default_factory=list, description="기술 스택·환경 요구사항"
    )


class Scenario(BaseModel):
    actor: str
    trigger: str
    steps: list[str] = Field(..., min_length=1)
    result: str
    evidence: Evidence


class Decision(BaseModel):
    category: DecisionCategory
    content: str
    rationale: Optional[str] = None
    evidence: Evidence


class Constraint(BaseModel):
    type: str = Field(..., description="일정 / 기술 / 범위 / 인력 / 기타")
    content: str
    evidence: Evidence


class MeetingExtraction(BaseModel):
    """LLM이 생성하는 부분. Instructor의 response_model로 씁니다."""

    project: Project
    users: list[UserGroup] = Field(default_factory=list)
    requirements: Requirements
    scenarios: list[Scenario] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    unresolved: list[str] = Field(
        default_factory=list,
        description="회의록에 근거가 없어 채우지 못한 항목과 그 이유",
    )


class MeetingStructured(MeetingExtraction):
    """저장·전달용 최종 형태. 시스템이 채우는 필드가 추가됩니다."""

    meeting_id: str
    validation_notes: list[str] = Field(
        default_factory=list,
        description="교차 규칙 검증에서 발견된 정합성 이슈. LLM이 채우지 않습니다.",
    )

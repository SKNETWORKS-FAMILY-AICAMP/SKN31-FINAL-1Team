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

from shared.schemas_base import Evidence
from enum import Enum


class DecisionCategory(str, Enum):
    FEATURE = "feature"
    NON_FUNCTIONAL = "non_functional"
    DATA = "data"
    TECH = "tech"
    SCOPE = "scope"

class ProjectGoal(BaseModel):
    """회의에서 확인된 프로젝트 목표."""

    content: str = Field(..., description="회의에서 확인된 프로젝트 목표",
    )

    evidence: Evidence = Field(..., description="프로젝트 목표를 뒷받침하는 회의록 원문",
    )


class ProjectProblem(BaseModel):
    """회의에서 확인된 개별 문제."""

    content: str = Field(..., description="회의에서 확인된 하나의 구체적인 문제",
    )

    evidence: Evidence = Field(..., description="개별 문제를 뒷받침하는 회의록 원문",
    )


class Project(BaseModel):
    """프로젝트의 기본 정보와 문제 및 목표."""

    name: str = Field(..., description="프로젝트명",
    )

    background: str = Field(..., description="프로젝트가 시작된 배경",
    )

    problem: str = Field(..., description="프로젝트에서 해결하려는 전체 문제를 요약한 문장",
    )

    problem_items: list[ProjectProblem] = Field(
        default_factory=list,
        description=(
            "회의에서 확인된 개별 문제 목록. "
            "서로 다른 문제를 하나의 항목으로 합치지 않습니다."
        ),
    )

    goals: list[ProjectGoal] = Field(
        default_factory=list,
        description="회의에서 확인된 프로젝트 목표와 원문 근거",
    )

    background_evidence: Evidence = Field(..., description="프로젝트 배경 문장의 근거",
    )

    problem_evidence: Evidence = Field(..., description="전체 문제 요약 문장의 근거",
    )

class UserGroup(BaseModel):
    type: str = Field(..., description="사용자 유형 (예: 서기, PM)")
    description: str
    needs: list[str] = Field(default_factory=list, description="이 사용자의 요구")
    evidence: Evidence


class RequirementItem(BaseModel):
    """
    일반 요구사항 항목입니다.

    priority는 노드 3에서 별도로 판단하므로 이곳에서 관리하지 않습니다.
    """

    content: str
    evidence: Evidence


class FunctionalRequirementItem(RequirementItem):
    """
    기능 요구사항 항목입니다.

    feature_name은 이 요구사항이 속하는 상위 기능명입니다.
    기능 사이의 관계를 문장으로 추측하지 않고 구조화된 값으로 전달합니다.
    """

    feature_name: Optional[str] = Field(
        default=None,
        max_length=40,
        description=(
            "이 요구사항이 속하는 상위 기능명. "
            "상위 기능 자체이면 자신의 기능명을 작성합니다. "
            "세부 동작이나 구현 조건이면 원문에서 확인되는 상위 기능명을 작성합니다. "
            "별도 외부 연동이면 해당 연동 기능명을 작성합니다. "
            "관계를 확인할 수 없으면 null로 둡니다."
        ),
    )


class Requirements(BaseModel):
    functional: list[FunctionalRequirementItem] = Field(
        default_factory=list,
        description="기능 요구사항",
    )
    non_functional: list[RequirementItem] = Field(
        default_factory=list,
        description="성능·보안·사용성 요구사항",
    )
    data: list[RequirementItem] = Field(
        default_factory=list,
        description="저장·연동 데이터 요구사항",
    )
    technical: list[RequirementItem] = Field(
        default_factory=list,
        description="기술 스택·환경 요구사항",
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
    rationale: Optional[str] = Field(
        default=None,
        description=(
            "이 결정을 내린 이유. 회의록에 이유가 언급된 경우에만 작성하고, "
            "없으면 비워 둡니다."
        ),
    )
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

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
    TECH = "tech"
    SCOPE = "scope"

class ProjectGoal(BaseModel):
    content: str = Field(
        ...,
        description="회의에서 확인된 프로젝트 목표",
    )
    evidence: Evidence = Field(
        ...,
        description="프로젝트 목표를 뒷받침하는 회의록 원문",
    )

class Project(BaseModel):
    """
    2026-09-07: evidence를 background_evidence/problem_evidence로 분리했습니다.

    예전엔 evidence 하나가 name+background+problem+goals 전체를 대표했습니다.
    문제는 이 넷 중 원문과 가장 잘 매칭되는 문장 하나로 evidence가 쏠린다는
    점입니다 — 실제 사례(리테일링크 기획안)에서 project.evidence가 goals
    쪽 문장으로 매칭됐는데, 노드②가 이걸 그대로 "개요"와 "문제 정의" 두
    섹션의 근거로 보여줘서 내용과 무관한 근거가 화면에 뜨는 문제가
    있었습니다. background와 problem은 노드②에서 서로 다른 섹션(1번 개요,
    2번 문제 정의)의 근거로 쓰이므로 각자 자기 근거를 가져야 합니다.

    goals는 아직 하류(노드②)가 근거로 쓰지 않아 분리하지 않았습니다.
    나중에 goals를 근거와 함께 보여줘야 하면 그때 추가하십시오.
    """
    name: str = Field(..., description="프로젝트명")
    background: str = Field(..., description="프로젝트 배경")
    problem: str = Field(..., description="해결하려는 문제")
    goals: list[ProjectGoal] = Field(default_factory=list, description="회의에서 확인된 프로젝트 목표와 원문 근거",)
    background_evidence: Evidence = Field(..., description="background 문장의 근거")
    problem_evidence: Evidence = Field(..., description="problem 문장의 근거")


class UserGroup(BaseModel):
    type: str = Field(..., description="사용자 유형 (예: 서기, PM)")
    description: str
    needs: list[str] = Field(default_factory=list, description="이 사용자의 요구")
    evidence: Evidence


class RequirementItem(BaseModel):
    """
    2026-09-07: priority 필드를 제거했습니다. 이 노드의 판단 기준이 프롬프트에
    없어 근거 없는 값이었고, 실제로 쓰는 하류는 노드③(requirement_draft)인데
    그쪽은 이미 자체 판단 기준(requirements_template.yaml)으로 priority를
    독립적으로 매기고 있어 이 필드를 참조하지 않습니다. 죽은 필드라 삭제합니다.
    """
    content: str
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
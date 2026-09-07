"""
노드 1 회의록 구조화 스키마.

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

# 회의에서 결정된 내용의 종류를 정의
class DecisionCategory(str, Enum):
    FEATURE = "feature"  # 어떤 기능을 만들기로 했는가
    TECH = "tech"        # 어떤 기술을 사용하기로 했는가 
    SCOPE = "scope"      # 무엇을 포함/제외하기로 했는가

# 프로젝트 관련 정보
class Project(BaseModel):
    name: str = Field(..., description="프로젝트명")
    background: str = Field(..., description="프로젝트 배경")
    problem: str = Field(..., description="해결하려는 문제")
    goals: list[str] = Field(..., min_length=1, description="프로젝트 목표")
    evidence: Evidence # 해당 내용의 근거가 되는 회의록 내용 보관

# 누가 사용하는지
class UserGroup(BaseModel):
    type: str = Field(..., description="사용자 유형 (예: 서기, PM)")
    description: str  # 해당 사용자의 설명
    needs: list[str] = Field(default_factory=list, description="이 사용자의 요구") 
    evidence: Evidence # 회의록 근거

# 요구사항 하나를 표현하는 단위
class RequirementItem(BaseModel):
    content: str   # 요구 사항 내용
    priority: Priority = Priority.MEDIUM  # 요구사항의 중요도(우선순위)
    evidence: Evidence  # 회의록 근거

# 요구사항을 묶는놓은 구조
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

# 사용자 시나리오
class Scenario(BaseModel):
    actor: str  # 행동하는 사용자
    trigger: str # 행동을 시작하게 된 상황
    steps: list[str] = Field(..., min_length=1) # 실제 행동 순서
    result: str  # 최종 결과
    evidence: Evidence # 회의록 근거

# 회의에서 실제로 결정 된 것.
class Decision(BaseModel):
    category: DecisionCategory    # 결정의 종류  # feature / tech / scope 사용 (만 허용)
    content: str    # 실제 결정 내용
    rationale: Optional[str] = None       # 왜 그렇게 결정했는지 (선택)
    evidence: Evidence   # 결정의 근거

# 제약조건
class Constraint(BaseModel):
    type: str = Field(..., description="일정 / 기술 / 범위 / 인력 / 기타")
    content: str  # ex) "3개월 안에 개발 해야 한다" 같은 내용
    evidence: Evidence

# LLM이 만들어야하는 답안지
class MeetingExtraction(BaseModel):
    """LLM이 생성하는 부분. Instructor의 response_model로 씁니다."""
    # 데이터 규칙 (결과를 MeetingExtraction 구조에 맞춰서 만들어라)
    project: Project 
    users: list[UserGroup] = Field(default_factory=list)
    requirements: Requirements
    scenarios: list[Scenario] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    # 회의에서 논의했지만 결론을 내리지 못한 내용을 기록
    unresolved: list[str] = Field( 
        default_factory=list,
        description="회의록에 근거가 없어 채우지 못한 항목과 그 이유",
    )


class MeetingStructured(MeetingExtraction):
    """저장·전달용 최종 형태. 시스템이 채우는 필드가 추가됩니다."""

    meeting_id: str    # 어떤 회의록에서 만들어 졌는지 식별을 위한 ID
    validation_notes: list[str] = Field(  # 검증 과정에서 발견된 문제 기록
        default_factory=list,
        description="교차 규칙 검증에서 발견된 정합성 이슈. LLM이 채우지 않습니다.",
    )

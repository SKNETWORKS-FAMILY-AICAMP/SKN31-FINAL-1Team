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

from typing import Literal, Optional

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

    # 2026-09-17 추가: background는 한 문단에 여러 사실(조사 결과, 현재
    # 방식, 진행 중인 작업 등)을 담는 경우가 많은데, background_evidence는
    # 처음부터 quote 1개만 받는 구조라 노드②(plan_draft)의 "프로젝트 개요"
    # 화면에 근거가 항상 1개만 표시됐다(신뢰하기 어렵다는 실사용 피드백).
    # background_evidence 자체를 리스트로 바꾸면 이걸 참조하는 기존 코드·
    # 테스트(schemas·validators·list_builder·fewshots 등 12개 파일)가
    # 전부 "단일 quote"를 가정하고 있어 다 같이 깨진다. 대신 이 필드를
    # 추가해서 이번 요구만 채운다 — 기존 필드·소비자는 전혀 안 건드림.
    background_evidence_extra: list[Evidence] = Field(
        default_factory=list,
        description=(
            "background에 background_evidence 하나로는 다 뒷받침하지 못하는 "
            "추가 사실이 있으면, 그 사실들을 뒷받침하는 원문 인용을 각각 "
            "하나씩 더 답합니다. background_evidence 하나로 충분하면 "
            "빈 배열로 둡니다. 없는 사실을 지어내 채우지 않습니다."
        ),
    )

    problem_evidence: Evidence = Field(..., description="전체 문제 요약 문장의 근거",
    )

class UserGroup(BaseModel):
    type: str = Field(..., description="사용자 유형 (예: 서기, PM)")
    description: str
    needs: list[str] = Field(default_factory=list, description="이 사용자의 요구")
    evidence: Evidence


class UserSignal(BaseModel):
    """사용자 프로필 합성용 원문 단서. 확인된 사용자 요구와 구분합니다."""

    kind: Literal["service_purpose", "user_action", "information_need"]
    actor: str = Field(default="", description="원문에 명시된 역할만 작성. 없으면 빈 문자열")
    content: str
    statement_status: Literal["stated", "proposed", "question", "rejected"]
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

    # 2026-09-13: Optional[str] = None에서 필수 필드로 바꿨습니다.
    #
    # 실행 결과 decisions 9건 전부 rationale이 비어 있었습니다. 회의록에는
    # 이유가 분명히 있었는데도(예: "예측 모델은 최소 6개월치 데이터가
    # 필요하나 신규 가입 고객은 데이터가 없다") 한 건도 채워지지 않았습니다.
    #
    # 프롬프트 규칙도 few-shot 예시 4건도 모두 정상이었으므로, 남은 원인은
    # 필드 형태입니다. 기본값이 있는 선택 필드는 구조화 출력에서 통째로
    # 생략되기 쉽습니다 — 모델이 항목마다 "이유가 있었나?"를 판단할 기회
    # 자체를 건너뜁니다.
    #
    # 필수로 두되 빈 문자열을 허용하면 판단은 강제하면서 지어내기는
    # 막을 수 있습니다. 이유가 없으면 ""를 쓰면 되고,
    # list_builder는 빈 문자열을 falsy로 보고 그대로 생략합니다.
    rationale: str = Field(
        ...,
        description=(
            "이 결정을 내린 이유. 회의록에 이유가 언급되어 있으면 "
            "반드시 작성합니다. 발언에 '때문에', '~라서', '~하므로', "
            "'~이 필요하나', '~가 없어서'처럼 근거를 밝히는 표현이 있거나 "
            "결정 직전에 그 결정을 뒷받침하는 설명이 나왔다면 이유가 "
            "언급된 것입니다. "
            "회의록에 이유가 없으면 빈 문자열로 둡니다. "
            "회의록에 없는 이유를 추론해서 채우지 않습니다. "
            # 2026-09-14: 측정 결과 15건 중 6건이 결정 내용을 바꿔 쓴
            # 문장이었습니다("발주서에 필요한 정보를 포함하기 위함").
            # 빈 문자열을 피하려는 동작이므로 여기서도 금지합니다.
            "content를 바꿔 쓴 문장은 이유가 아닙니다. "
            "이유는 content에 없는 정보를 담고 있어야 하며, "
            "그런 정보가 회의록에 없으면 빈 문자열을 씁니다."
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
    user_signals: list[UserSignal] = Field(default_factory=list)
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

"""
노드 ② 기획서 생성 스키마 — 7개 섹션.

## 섹션 구성

| # | key         | 섹션            | 유형      | 생성 |
|---|-------------|-----------------|-----------|------|
| 1 | overview    | 프로젝트 개요   | narrative | LLM  |
| 2 | problem     | 문제 정의       | narrative | LLM  |
| 3 | users       | 대상 사용자     | narrative | LLM  |
| 4 | features    | 주요 기능       | narrative | LLM  |
| 5 | scenarios   | 사용자 시나리오 | narrative | LLM  |
| 6 | tech_scope  | 기술 스택 및 제약사항 | list | 코드 |
| 7 | decisions   | 최종 결정사항   | list      | 코드 |

## 12개에서 7개로 줄인 내역

- 프로젝트 목표 → 삭제 (개요·문제 정의와 내용이 겹침)
- 기능/비기능/데이터 요구사항 → 삭제 (실무 기획서에 상세 명세를 담지 않음)
- 기술 요구사항 + 서비스 범위·제약 → 6번으로 통합

## 스키마가 두 개인 이유

PlanSections     : LLM이 생성하는 서술형 5개만
PlanDocument     : 위 + 코드가 조립하는 2개 + 시스템 필드

is_incomplete 같은 시스템 필드를 LLM 스키마에 넣으면
모델이 "이것도 채워야 하나?" 하고 뭔가 써넣습니다.
아예 보여주지 않는 게 안전합니다.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from shared.schemas_base import Evidence, ReviewStatus


class SectionType(str, Enum):
    NARRATIVE = "narrative"   # LLM 작문 — 반려 시 재생성이 의미 있음
    LIST = "list"             # 코드 조립 — 재생성해도 같은 결과


# ─────────────────────────────────────────────────────────────
# 섹션 정의 — 이 표가 노드 ②의 설계도입니다.
# 프롬프트와 조립 코드 양쪽이 이걸 참조합니다.
# ─────────────────────────────────────────────────────────────
SECTION_SPEC = [
    {"no": 1, "key": "overview",   "title": "프로젝트 개요",
     "type": SectionType.NARRATIVE,
     "source_fields": ["project.name", "project.background"]},

    {"no": 2, "key": "problem",    "title": "문제 정의",
     "type": SectionType.NARRATIVE,
     "source_fields": ["project.problem"]},

    {"no": 3, "key": "users",      "title": "대상 사용자",
     "type": SectionType.NARRATIVE,
     "source_fields": ["users"]},

    {"no": 4, "key": "features",   "title": "주요 기능",
     "type": SectionType.NARRATIVE,
     "source_fields": ["requirements.functional", "decisions[feature]"]},

    {"no": 5, "key": "scenarios",  "title": "사용자 시나리오",
     "type": SectionType.NARRATIVE,
     "source_fields": ["scenarios"]},

    {"no": 6, "key": "tech_scope", "title": "기술 스택 및 제약사항",
     "type": SectionType.LIST,
     "source_fields": ["requirements.technical", "decisions[tech]", "constraints"]},

    {"no": 7, "key": "decisions",  "title": "최종 결정사항",
     "type": SectionType.LIST,
     "source_fields": ["decisions"]},
]

NARRATIVE_KEYS = [s["key"] for s in SECTION_SPEC if s["type"] == SectionType.NARRATIVE]
LIST_KEYS = [s["key"] for s in SECTION_SPEC if s["type"] == SectionType.LIST]


class NarrativeSection(BaseModel):
    """LLM이 생성하는 서술형 섹션."""
    key: str
    content_html: str = Field(
        ...,
        description="원본이 비어 있으면 빈 문자열(''). 추론해서 채우지 말 것.",
    )
    evidence: list[Evidence] = Field(default_factory=list)

    # 반려 사유를 다 반영하지 못했을 때 그 이유를 적습니다.
    #
    # 재생성을 요청받았는데 원본에 정보가 없으면 지어내는 대신
    # "무엇이 없어서 못 채웠는지"를 여기 적게 합니다.
    # 이게 없으면 작성자는 반려했는데 결과가 그대로인 이유를 알 수 없습니다.
    needs_input: str = Field(
        default="",
        description=(
            "반려 사유 중 원본 정보가 없어 반영하지 못한 부분. "
            "전부 반영했으면 빈 문자열."
        ),
    )


class PlanSections(BaseModel):
    """LLM 응답 형태. Instructor의 response_model로 씁니다."""
    sections: list[NarrativeSection] = Field(..., min_length=1)


class Review(BaseModel):
    state: ReviewStatus = ReviewStatus.PENDING
    comment: Optional[str] = None
    reject_type: Optional[str] = None   # 사실 오류 / 내용 부족 / 표현 문제 / 회의록 자체 문제


class PlanSection(BaseModel):
    """저장·전달용 최종 섹션 형태."""
    no: int
    key: str
    title: str
    section_type: SectionType
    content_html: str

    # 같은 내용의 태그 없는 배열.
    # 화면은 content_html, 하류 노드(③)는 items를 씁니다.
    # 서술형 섹션(문단)은 쪼갤 항목이 없어 빈 배열입니다.
    items: list[str] = Field(default_factory=list)

    source_fields: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)

    # 반려 사유 중 반영하지 못한 부분 (재생성 시에만 채워짐)
    needs_input: str = ""

    # 아래 세 필드는 코드가 채웁니다. LLM이 건드리지 않습니다.
    is_incomplete: bool = False
    edited_by_pm: bool = False
    review: Review = Field(default_factory=Review)


class PlanDocument(BaseModel):
    proposal_id: str
    meeting_id: str
    status: str = "draft"          # draft | in_review | approved | rejected
    sections: list[PlanSection]
    unresolved: list[str] = Field(default_factory=list)

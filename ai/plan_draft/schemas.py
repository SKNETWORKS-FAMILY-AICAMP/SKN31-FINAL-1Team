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


class Feature(BaseModel):
    """
    4번 주요 기능의 항목 하나.

    프론트 수정 화면이 항목 단위로 편집하는 구조라
    HTML 덩어리가 아니라 배열로 담습니다.
    """
    title: str = Field(..., max_length=40, description="기능명. 30자 내외.")
    description: str = Field(
        ...,
        description="이 기능이 무엇인지 2~3문장. 원본에 없는 내용을 추가하지 말 것.",
    )
    # 2026-09-07: priority 필드를 제거했습니다.
    #
    # 예전엔 "노드③이 근거 없이 매기지 않도록" 여기서 넘겨주려 했지만,
    # 이 값 자체가 노드①/②에서 기준 없이(프롬프트에 판단 규칙 없이) 매겨진
    # 근거 없는 값이었습니다. 게다가 노드③(requirement_draft)은 이미
    # 자체 판단 기준(requirements_template.yaml의 [priority 판단 규칙])으로
    # priority를 독립적으로 매기고 있어 이 필드를 참조하지 않습니다.
    # 쓰이지 않는 근거 없는 값을 굳이 들고 다닐 이유가 없어 삭제합니다.


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

    # 4번 주요 기능만 별도 배열로 받습니다.
    # sections 안에 HTML로 넣으면 프론트가 항목별로 편집할 수 없습니다.
    features: list[Feature] = Field(
        default_factory=list,
        min_length=0, max_length=7,
        description="주요 기능 3~7개. 원본에 기능 정보가 없으면 빈 배열.",
    )


class Review(BaseModel):
    state: ReviewStatus = ReviewStatus.PENDING
    comment: Optional[str] = None
    reject_type: Optional[str] = None   # 사실 오류 / 내용 부족 / 표현 문제 / 회의록 자체 문제


class VerifiedEvidence(BaseModel):
    """
    저장·화면 표시용 근거. LLM 응답 스키마(NarrativeSection.evidence)와는 다른 모델입니다.

    NarrativeSection.evidence는 LLM이 스스로 "이게 근거예요"라고 내놓은 것이라
    원문과 실제로 대조된 적이 없습니다(자기 인용, 검증 안 됨). 반면 이 모델은
    노드①이 verify_and_mark()로 이미 원문 대조를 마친 근거를 코드가 그대로
    재사용해 채우는 것이라 status가 실제 검증 결과를 반영합니다.

    status에 default를 주지 않은 이유: 코드가 항상 명시적으로 채웁니다.
    LLM 스키마가 아니므로 "이것도 채워야 하나" 문제가 없습니다.
    """
    quote: str
    status: str  # "verified" | "unverified" — ai/meeting_analysis/validators/evidence.py 값과 동일


class TechScopeGroup(BaseModel):
    """
    6번(기술 및 제약사항) 전용 소제목 단위 묶음.

    2026-09-07 추가: 지금까지 items는 소제목 구분 없이 전부 하나로 flat하게
    담겨 있었습니다. 화면(읽기/수정)에서 "기술 스택 소제목 아래 항목들",
    "제약사항 소제목 아래 항목들"처럼 구분해서 보여주고 편집하려면 이 구분이
    필요합니다 — content_html을 HTML로 렌더링하는 대신 구조 그대로 저장·표시
    하기로 한 결정에 따른 것입니다(프론트 전달사항 문서 참고).

    회의에서 안 나온 소제목은 애초에 항목이 없으므로 groups 배열에도
    포함되지 않습니다(list_builder.build_tech_scope의 기존 동작과 동일).
    """
    subtitle: str
    items: list[str]


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

    # 2026-09-07: LLM이 자체 생성하는 NarrativeSection.evidence(Evidence, 검증 안 됨)를
    # 그대로 쓰지 않습니다. 대신 노드①이 이미 원문 대조를 마친 근거를 source_fields
    # 경로로 재수집합니다(list_builder.collect_source_evidence). 그래서 여기 타입은
    # status를 갖는 VerifiedEvidence입니다 — quote만 있는 Evidence가 아닙니다.
    evidence: list[VerifiedEvidence] = Field(default_factory=list)

    # 4번 주요 기능 전용. 다른 섹션은 빈 배열입니다.
    # 프론트가 항목 단위로 편집하고, 노드 ③이 파싱 없이 사용합니다.
    features: list[Feature] = Field(default_factory=list)

    # 6번 기술 및 제약사항 전용. 다른 섹션은 빈 배열입니다.
    # items를 소제목별로 묶은 것 — 프론트가 소제목 단위로 편집합니다.
    groups: list[TechScopeGroup] = Field(default_factory=list)

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
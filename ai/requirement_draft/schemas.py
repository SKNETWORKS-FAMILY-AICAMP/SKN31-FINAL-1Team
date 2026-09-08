"""
requirement_draft/schemas.py

컨텍스트 설계 요약
  - 입력: A1-2 출력(기획서 JSON), State Passing
  - 정적 참고자료: requirements_template.yaml, nfr_checklist.yaml
  - Tools: 없음
  - 출력: 요구사항정의서 JSON
"""

from enum import Enum
from typing import List, Optional

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

from shared.schemas_base import Priority, ReviewStatus


class ReqType(str, Enum):
    FUNCTIONAL = "기능"
    NON_FUNCTIONAL = "비기능"


class Source(str, Enum):
    """
    이 요구사항이 어디서 왔는지 — shared.schemas_base.Source(회의록추출/
    사람입력/시스템생성)와는 다른 축의 구분이라 여기 따로 둔다. 여긴
    "기획서 본문에서 직접 도출했는지, 표준 체크리스트 기본값으로 채웠는지"만
    구분하면 된다.
    """

    REQUIREMENT_TEXT = "requirement_text"
    BASELINE_DEFAULT = "baseline_default"


class ItemReviewStatus(str, Enum):
    """
    요구사항 항목 1건 단위의 확신도 표시 — shared.schemas_base.ReviewStatus
    (문서 전체 승인/반려 게이트 상태, pending/approved/rejected)와는 다른
    개념이다. 이건 "AI가 이 항목을 확신을 갖고 채웠는지, PM 확인이
    필요한지"만 나타낸다. RequirementDocumentOutput.review_status(문서 단위
    게이트)는 계속 공용 ReviewStatus를 쓴다 — 그건 정말 같은 개념이라서.
    """

    CONFIRMED = "검토완료"
    PENDING = "검토대기"


class PlanRequirement(BaseModel):
    """
    PlanDocument 내부의 요구사항 항목.
    views.py 등에서 'id' / 'title' / 'description' 키로 입력되는 경우를 모두 수용하도록 AliasChoices 적용.
    """
    req_id: str = Field(..., validation_alias=AliasChoices("req_id", "id"))
    content: str = Field(..., validation_alias=AliasChoices("content", "title", "description"))

    class Config:
        populate_by_name = True


class PlanDocument(BaseModel):
    """
    A1-2가 생성한 기획서 JSON.

    아래 5개 필드(overview/background/target_users/key_features/
    tech_constraints)는 requirements/views.py의 RequirementExtractView가
    SpecDocument에서 직접 읽어 plan_dict에 담아 보내는 필드
    """

    project_id: str
    meeting_id: Optional[str] = None
    title: str
    goal: str
    overview: str = ""
    background: str = ""
    target_users: str = ""
    key_features: str = ""
    # SpecDocument엔 tech_constraints란 필드가 없다(실제론 tech_stack) — views.py가
    # 존재하지 않는 속성명으로 읽으려다 매번 getattr 기본값(빈 리스트)만 보내는
    # 상태라, 지금 당장은 항상 빈 리스트로 들어온다는 전제로 타입만 맞춰둔다.
    tech_constraints: List[str] = Field(default_factory=list)
    requirements: List[PlanRequirement] = Field(..., min_length=1)
    pipeline_stage: Optional[str] = None


class RequirementItem(BaseModel):
    """
    요구사항 1건. 3-depth(대분류>중분류>소분류=title).

    category_1(대분류)은 "기능"/"비기능" 두 값만 존재한다 — LLM이 채운 값을
    믿지 않고, validate_consistency()가 type에서 그대로 확정한다(2026-09-08,
    이미 ID 포맷으로 이중 검증되는 type을 그대로 쓰는 게 LLM이 매번 정확히
    맞히길 기대하는 것보다 안전하다). category_2(중분류)가 실제 그룹을
    나타낸다 — 기능은 기능 그룹명(예: "재고 관리"), 비기능은 NFR 표준
    카테고리명(예: "보안성")이 들어가며, 이제 둘 다 필수다(예전엔 비기능의
    category_2를 null로 강제했었는데, 화면 분류 표시 요구사항에 맞춰 뒤집었다).
    """

    id: str
    category_1: str
    category_2: str
    title: str
    description: str
    type: ReqType
    priority: Optional[Priority] = None
    source: Source
    review_status: ItemReviewStatus

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, v):
        """AI가 'High', 'HIGH' 등 대소문자를 다르게 반환할 경우 Enum 매핑"""
        if isinstance(v, str):
            v_upper = v.upper()
            for p in Priority:
                if p.name == v_upper or str(p.value).upper() == v_upper:
                    return p
        return v

    @field_validator("id")
    @classmethod
    def validate_id_format(cls, v: str) -> str:
        import re

        if not re.fullmatch(r"N?FR-\d{2}-\d{3}", v):
            raise ValueError(f"ID 포맷 오류: {v}")
        return v

    @model_validator(mode="after")
    def validate_consistency(self):
        is_nfr_id = self.id.startswith("NFR-")
        if is_nfr_id and self.type != ReqType.NON_FUNCTIONAL:
            raise ValueError(f"{self.id}: NFR- ID인데 type이 '{self.type.value}'입니다")
        if not is_nfr_id and self.type != ReqType.FUNCTIONAL:
            raise ValueError(f"{self.id}: FR- ID인데 type이 '{self.type.value}'입니다")

        # category_1은 LLM이 뭘 채웠든 상관없이 type에서 코드가 그대로 확정한다 —
        # "기능"/"비기능" 두 값만 존재하는 필드를 매번 LLM이 정확히 맞히길
        # 기대하는 것보다, 이미 ID 포맷으로 검증된 type을 그대로 쓰는 게 안전하다.
        self.category_1 = self.type.value

        if not self.category_2 or not self.category_2.strip():
            raise ValueError(
                f"{self.id}: category_2는 비어있으면 안 됩니다 "
                f"(기능은 기능 그룹명, 비기능은 NFR 카테고리명을 넣어야 함)"
            )

        is_pending = self.review_status == ItemReviewStatus.PENDING

        if self.priority is None and not is_pending:
            raise ValueError(f"{self.id}: priority가 비었으면 검토대기여야 합니다")

        if self.source == Source.BASELINE_DEFAULT and not is_pending:
            raise ValueError(f"{self.id}: baseline_default 항목은 검토대기여야 합니다")

        return self


class RequirementDocument(BaseModel):
    requirements: List[RequirementItem] = Field(..., min_length=1)

    @field_validator("requirements")
    @classmethod
    def validate_unique_ids(cls, v: List[RequirementItem]) -> List[RequirementItem]:
        ids = [item.id for item in v]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            raise ValueError(f"요구사항 ID 중복: {sorted(dup)}")
        return v


class RequirementDocumentOutput(BaseModel):
    """다음 노드(A2-2) 전달 및 DB 저장용 최종 형태."""

    project_id: str
    plan_id: Optional[str] = None
    requirements: List[RequirementItem]
    review_status: ReviewStatus = ReviewStatus.PENDING

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

from shared.schemas_base import Priority, ReviewStatus, Source


class ReqType(str, Enum):
    FUNCTIONAL = "기능"
    NON_FUNCTIONAL = "비기능"


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
    """A1-2가 생성한 기획서 JSON. (a1_2_plan_draft.schemas.PlanDocument와 동일 계약)"""

    project_id: str
    meeting_id: Optional[str] = None
    title: str
    goal: str
    requirements: List[PlanRequirement] = Field(..., min_length=1)
    pipeline_stage: Optional[str] = None


class RequirementItem(BaseModel):
    """요구사항 1건. 3-depth(대분류>중분류>소분류=name), 비기능은 category_2 생략."""

    id: str
    category_1: str
    category_2: Optional[str] = None
    name: str
    description: str
    type: ReqType
    priority: Optional[Priority] = None
    source: Source
    review_status: ReviewStatus

    # --- AI 출력값 유연성 확보용 Pre-validators ---

    @field_validator("review_status", mode="before")
    @classmethod
    def normalize_review_status(cls, v):
        """AI가 한글 '검토대기'를 반환할 경우 'pending' Enum 값으로 자동 변환"""
        if v == "검토대기":
            return "pending"
        elif v == "승인":
            return "approved"
        elif v == "반려":
            return "rejected"
        return v

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, v):
        """AI가 'baseline_default' 문자열을 넘겨줄 때 Enum 호환성을 위한 정규화"""
        if isinstance(v, str) and v.lower() == "baseline_default":
            if hasattr(Source, "BASELINE_DEFAULT"):
                return getattr(Source, "BASELINE_DEFAULT")
            return getattr(Source, "SYSTEM", v)
        return v

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

    # --- 기존 Validation 로직 ---

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
        if self.type == ReqType.NON_FUNCTIONAL and self.category_2 is not None:
            raise ValueError(f"{self.id}: 비기능요구사항의 category_2는 null이어야 합니다")
        
        # 안전한 review_status 검사 (pending 판별)
        is_pending = self.review_status == ReviewStatus.PENDING or str(getattr(self.review_status, "value", self.review_status)) in ["pending", "검토대기"]

        if self.priority is None and not is_pending:
            raise ValueError(f"{self.id}: priority가 비었으면 검토대기여야 합니다")
        
        # Source.BASELINE_DEFAULT AttributeError 예방 조치
        baseline_val = getattr(Source, "BASELINE_DEFAULT", "baseline_default")
        current_source_val = getattr(self.source, "value", self.source)
        
        if (self.source == baseline_val or current_source_val == "baseline_default") and not is_pending:
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
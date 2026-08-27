"""
공통 스키마 요소.

※ 이 파일은 여나가 제안 형태로 먼저 채운 것입니다.
  담당이 정해지지 않아 노드 ① 작업이 막혀 있어 최소 형태로 만들었습니다.
  각 노드 담당자가 필요에 맞게 고치거나 추가하세요.

※ Evidence는 원래 목록(Priority, ReviewStatus, Source)에 없었지만
  meeting_analysis / plan_draft / requirement_draft 세 곳에서 모두 쓰이므로
  여기 두는 것이 맞다고 판단해 추가했습니다. 이견 있으면 알려주세요.
"""

from enum import Enum

from pydantic import BaseModel, Field


class Priority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReviewStatus(str, Enum):
    """게이트에서의 검토 상태."""
    PENDING = "pending"      # 아직 검토 안 함
    APPROVED = "approved"    # 승인
    REJECTED = "rejected"    # 반려 (사유 필요)


class Source(str, Enum):
    """
    이 데이터가 어디서 왔는지.

    회의록 근거로 AI가 뽑은 것과 사람이 직접 넣은 것을 구분합니다.
    PM이 기획서에 회의록에 없던 내용을 추가할 수 있으므로,
    하류 노드가 "이건 회의에서 나온 게 아니다"를 알 수 있어야 합니다.
    """
    MEETING = "meeting"   # 회의록에서 추출 (evidence 있음)
    USER = "user"         # 사람이 직접 입력 (evidence 없음)
    SYSTEM = "system"     # 시스템이 생성 (ID, 상태값 등)


class Evidence(BaseModel):
    """
    추출한 정보의 근거.

    quote는 회의록 원문에 그대로 존재하는 문장이어야 합니다.
    화면에는 표시하지 않고, 검증과 디버깅에만 씁니다.
    """
    quote: str = Field(
        ...,
        min_length=5,
        max_length=200,
        description="회의록 원문에 그대로 존재하는 문장. 요약·의역 금지.",
    )

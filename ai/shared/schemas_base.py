"""
shared/schemas_base.py

여러 에이전트의 출력 스키마에서 공통으로 쓰이는 Enum·베이스 타입.
각 에이전트의 schemas.py는 이 파일의 타입을 재사용하고,
그 에이전트만의 고유 필드만 추가로 정의한다.
"""

from enum import Enum


class Priority(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class ReviewStatus(str, Enum):
    PENDING = "검토대기"
    DONE = "검토완료"


class Source(str, Enum):
    """이 값이 어디서 도출되었는지 추적하기 위한 공통 필드.

    A2-1(요구사항정의서), A2-2(업무), A2-3(담당자추천) 등
    사람 검토가 필요한 모든 생성 결과에 공통으로 붙인다.
    """

    REQUIREMENT_TEXT = "requirement_text"   # 입력 원문에서 직접 도출
    BASELINE_DEFAULT = "baseline_default"   # 표준 체크리스트 등 기본값으로 생성
    RULE_FILTERED = "rule_filtered"         # 코드 규칙(1차 필터링) 결과 기반

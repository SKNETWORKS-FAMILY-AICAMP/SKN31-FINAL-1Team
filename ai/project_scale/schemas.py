"""
project_scale/schemas.py

컨텍스트 설계 요약
  - 입력: 기획서(SpecDocument) 상위 맥락 5개 필드(overview/problem_definition/
    key_features/tech_stack/final_decisions) — backend가 dict로 조립해 넘긴다.
    개별 요구사항 항목이 아니라 기획서 단계의 "전체 그림"을 본다 — 그래야
    task_generation이 이미 쪼갠 업무 단위 합산(team_sizing.py)으로는 못 잡는
    신규 기술 도입/외부 연동/미확정 사항 같은 정성적 리스크를 볼 수 있다.
  - 정적 참고자료: 복잡도 판단 few-shot(하/중/상 각 1건)
  - Tools: 없음
  - 출력: 복잡도 등급(하/중/상) + 근거 문장. 실제 인원수 계산(버퍼 적용)은
    이 모듈이 아니라 team_sizing.apply_complexity_buffer()(순수 코드)가 한다 —
    "코드가 결정, LLM은 서술만" 원칙. task_generation의 difficulty Enum과
    동일한 패턴(LLM은 등급만 고르고, 등급→숫자 변환은 코드의 고정 매핑표가 함).
"""

from enum import Enum

from pydantic import BaseModel, Field


class ComplexityLevel(str, Enum):
    LOW = "하"
    MEDIUM = "중"
    HIGH = "상"


class ProjectScaleAssessment(BaseModel):
    complexity: ComplexityLevel
    complexity_reason: str = Field(
        ...,
        description="왜 이 등급인지 구체적 근거 — PM 화면에 그대로 노출됨. "
        "'복잡함' 같은 추상적 표현 대신 어떤 요소(신규 기술/외부 연동/미확정 사항 등) 때문인지 서술하라.",
    )

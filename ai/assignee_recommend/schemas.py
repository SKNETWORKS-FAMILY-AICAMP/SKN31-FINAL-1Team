"""
a2_3_assignee_recommend/schemas.py

컨텍스트 설계 요약
  - 입력: 업무 정보(A2-2 출력 중 1건) + 팀원 이력·부하도 — SQL 조회
  - 방식: 하이브리드 — 기술스택·업무량은 코드(규칙)로 1차 필터링,
          LLM은 필터링된 후보에 대한 근거 문장 생성만 담당
  - Tools: 없음
  - 출력: 추천 담당자 + 근거 (근거 없으면 보류)
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class CandidateFeatures(BaseModel):
    """1차 필터링(코드)이 끝난 뒤, LLM에게 근거 문장만 생성시키기 위해 넘기는 정보."""

    employee_id: str
    skill_match: str = Field(..., description="코드가 계산한 기술 적합도 서술 (예: 'React 경력 2년')")
    workload: str = Field(..., description="코드가 계산한 현재 업무량 서술")
    similar_experience: str = Field(..., description="유사 업무 완료 이력 서술")
    rule_score: float = Field(..., description="코드가 계산한 1차 점수 (LLM이 그대로 참고)")


class RecommendationReason(BaseModel):
    skill_fit: str
    workload: str
    similar_experience: str


class Recommendation(BaseModel):
    rank: int
    employee_id: str
    score: float
    reason: RecommendationReason


class RecommendationList(BaseModel):
    task_id: str
    recommendations: List[Recommendation] = Field(default_factory=list)
    # 규칙 필터링 결과 후보가 하나도 없으면 빈 리스트 — 이때 review_status는 보류 처리
    review_required: bool = False

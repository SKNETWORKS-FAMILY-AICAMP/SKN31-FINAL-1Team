"""
assignment_explanation/schemas.py

2026-09-11 (Phase 4 item 13): 확정된 배분 계획을 PM에게 브리핑하는 LLM 출력.

이 에이전트는 계획을 바꾸지 않는다 — 담당자·날짜·공수는 이미 결정적으로
확정됐고, 여기서는 그 계획을 읽고 "PM이 뭘 주의해야 하는지"만 요약한다.
개별 배정 근거(skill_fit/workload 등)는 assignee_recommend가 이미 만든다.
"""

from typing import List

from pydantic import BaseModel, Field


class PlanBriefing(BaseModel):
    risks: List[str] = Field(
        default_factory=list,
        description="이 배분 계획에서 PM이 주의할 리스크 2~4개. 각 한 문장, 구체적으로.",
    )
    checkpoints: List[str] = Field(
        default_factory=list,
        description="PM이 확정 전 또는 진행 중 확인·결정해야 할 사항 0~3개. 없으면 빈 리스트.",
    )

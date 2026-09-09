"""
project_scale/agent.py

프로젝트 복잡도 판단 (team_sizing 보완)

team_sizing.estimate_team_size()는 task_generation이 이미 쪼갠 업무의
estimated_hours만 기계적으로 합산한다 — "이 프로젝트가 전체적으로 얼마나
크고 복잡한가"에 대한 판단이 전혀 없다(2026-09-09 확인). 이 모듈은 기획서
(SpecDocument) 상위 맥락(overview/tech_stack/final_decisions 등)을 보고
복잡도 등급(하/중/상)만 판단한다.

실제 인원수 보정(버퍼 곱셈)은 여기서 하지 않는다 — 그건
team_sizing.apply_complexity_buffer()(순수 코드, 고정 매핑표)의 책임이다
("코드가 결정, LLM은 서술만" 원칙 — task_generation의 difficulty Enum과
동일한 패턴: LLM은 등급만 고르고, 등급→숫자 변환은 코드가 한다).

이 모듈은 DB를 모른다 — SpecDocument 조회는 호출부(Django) 책임이고,
그 결과를 project_context dict로 조립해 넘긴다는 전제다.
"""

import logging

from shared.llm_client import create_structured
from shared.retry_config import DEFAULT_MAX_TOKENS, MAX_RETRIES, TEMPERATURE_STRUCTURED

from .prompt_builder import build_complexity_prompt
from .schemas import ProjectScaleAssessment

logger = logging.getLogger(__name__)


def assess_project_complexity(project_context: dict) -> ProjectScaleAssessment:
    """
    project_context: {"overview", "problem_definition", "key_features",
    "tech_stack", "final_decisions"} — SpecDocument 필드 그대로(backend가 조립).
    """
    prompt = build_complexity_prompt(project_context)
    return create_structured(
        system_prompt=prompt,
        user_message="위 기획서 요약을 보고 이 프로젝트의 복잡도 등급과 근거를 판단하라.",
        response_model=ProjectScaleAssessment,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=TEMPERATURE_STRUCTURED,
        max_retries=MAX_RETRIES,
    )

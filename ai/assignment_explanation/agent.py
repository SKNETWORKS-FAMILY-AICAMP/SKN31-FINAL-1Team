"""
assignment_explanation/agent.py

2026-09-11 (Phase 4 item 13): 확정된 배분 계획을 한 번의 LLM 호출로 브리핑한다.

입력은 계획 "요약"이다 — 전체 suggestion을 다 보내지 않는다(토큰 절약 + 판단에
필요한 신호만). 호출이 실패하면 빈 브리핑을 반환한다(파이프라인을 막지 않는다).
개별 배정/일정 근거는 이미 다른 곳에서 만들어지므로 여기서는 다루지 않는다.
"""

import json
import logging
from typing import Any, Dict

from pydantic import ValidationError

from shared.llm_client import create_structured
from shared.retry_config import DEFAULT_MAX_TOKENS, MAX_RETRIES, TEMPERATURE_GENERATIVE

from .schemas import PlanBriefing

logger = logging.getLogger(__name__)


def _prompt(context: Dict[str, Any]) -> str:
    return f"""너는 방금 만들어진 프로젝트 업무 배분 계획을 검토해, PM이 확정 전에
알아야 할 것을 짧게 브리핑한다. 계획 자체는 이미 확정됐으니 바꾸려 하지 마라.

주의해서 볼 신호:
  - 복잡도 등급과 그 이유
  - 일정이 프로젝트 종료일을 넘겼는지(exceeds), 버퍼가 얼마나 남았는지
  - 배정 보류된 업무(held) — 조건 맞는 담당자가 없어서 사람이 직접 정해야 함
  - 특정 담당자에게 과도하게 몰렸는지
  - 여러 명이 나눠 맡게 된 기능(splits)과 그 이유
  - 선행 관계가 많아 일정이 줄줄이 밀릴 위험

risks는 2~4개, 각각 구체적인 한 문장. checkpoints는 PM이 실제로 확인/결정해야
하는 것만(예: "9월 7일까지 결제 정책 확정 여부 확인"). 해당 없으면 빈 리스트.

[배분 계획 요약]
{json.dumps(context, ensure_ascii=False, indent=2)}
"""


def summarize_plan(context: Dict[str, Any]) -> PlanBriefing:
    """
    context 예시 키:
      complexity: {"grade": "중", "reason": "..."} | None
      schedule: {"projected_finish_date", "project_end_date", "project_buffer_days", "exceeds_project_period"}
      total_units, assigned_units, held_units: [{"title", "reason"}]
      over_period_units: [{"title", "assignee_name"}]
      package_splits: [{"reason"}]
      assignee_load: [{"assignee_name", "hours", "unit_count"}]  # 상위 몇 명
    """
    try:
        return create_structured(
            system_prompt=_prompt(context),
            user_message="이 배분 계획을 브리핑하라.",
            response_model=PlanBriefing,
            max_tokens=DEFAULT_MAX_TOKENS,
            temperature=TEMPERATURE_GENERATIVE,
            max_retries=MAX_RETRIES,
        )
    except ValidationError as e:
        logger.warning("계획 브리핑 스키마 검증 실패 — 빈 브리핑: %s", e)
        return PlanBriefing()
    except Exception as e:
        logger.warning("계획 브리핑 LLM 호출 실패 — 빈 브리핑: %s", e)
        return PlanBriefing()

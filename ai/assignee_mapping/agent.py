"""
assignee_mapping/agent.py

담당자 매핑 (신규 — 업무 자동 생성(A2-2)과 업무 배정(A2-3) 사이)
사원 원본 데이터(User+UserSkill+UserCertification) 중 경력기술서 원문
(past_projects)만 LLM으로 해석해 짧은 경험 태그로 바꾸고, 이미 구조화된
skills는 그대로 통과시켜 A2-3(assignee_recommend)이 바로 쓸 수 있는
EmployeeFitnessProfile을 만든다.

이 모듈은 DB를 모른다 — User+UserSkill+UserCertification 조회는 호출부
(Django/Celery task)의 책임이고, 그 결과를 state["raw_employee_profiles"]에
채워 넣어 전달한다는 전제다 (ai/ ↔ backend 통합 방식 B안, 2026-08-30 결정).

후보 필터링(재직 여부/필요 직무/필요 기술)은 호출부가 SQL로 미리 걸러주는 게
아니라, 이 에이전트가 rule_filter.filter_candidates()로 직접 한다(2026-09-02
결정) — 호출부는 필터링 없이 사원 원본 데이터를 그대로 넘기면 된다.
"""

import logging
from functools import lru_cache
from typing import Any, Dict, List

from pydantic import ValidationError

from shared.llm_client import create_structured
from shared.retry_config import DEFAULT_MAX_TOKENS, MAX_RETRIES, TEMPERATURE_STRUCTURED

from .prompt_builder import build_extraction_prompt
from .rule_filter import filter_candidates
from .schemas import EmployeeFitnessProfile, ExtractedExperienceTags, RawEmployeeProfile

logger = logging.getLogger(__name__)


# 프롬프트에 실제로 들어가는 변수는 career_history_text 하나뿐이다(prompt_builder.py
# 참고 - job_role/skills는 여기 관여 안 함). 그런데 같은 사원의 경력기술서는 거의
# 안 바뀌는데도 업무 배분 실행을 누를 때마다 전체 후보를 매번 새로 LLM에 태워서
# TPM 레이트리미트의 주범이 되었다 - 프로세스 생존 기간 동안만이라도 같은 원문이면
# 재호출하지 않도록 캐싱한다. RawEmployeeProfile 자체는 해시 불가능하니 문자열
# career_history_text만 키로 쓴다.
@lru_cache(maxsize=512)
def _extract_experience_tags_cached(career_history_text: str) -> ExtractedExperienceTags:
    prompt_profile = RawEmployeeProfile(
        employee_id="", employee_no="", name="", job_role="", is_active=True,
        career_history_text=career_history_text,
    )
    prompt = build_extraction_prompt(prompt_profile)
    return create_structured(
        system_prompt=prompt,
        user_message="위 경력기술서에서 경험 태그를 추출하라.",
        response_model=ExtractedExperienceTags,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=TEMPERATURE_STRUCTURED,
        max_retries=MAX_RETRIES,
    )


def extract_experience_tags(profile: RawEmployeeProfile) -> ExtractedExperienceTags:
    """career_history_text가 비어있으면 LLM 호출 없이 바로 빈 태그를 반환한다."""
    if not profile.career_history_text.strip():
        return ExtractedExperienceTags(tags=[])

    return _extract_experience_tags_cached(profile.career_history_text)


def assignee_mapping_node(state: Dict[str, Any]) -> Dict[str, Any]:
    missing = [k for k in ("raw_employee_profiles", "tasks", "needed_roles") if k not in state]
    if missing:
        return {"error": f"MISSING_INPUT: state{missing} — 호출부가 미리 채워야 함"}

    try:
        raw_profiles = [RawEmployeeProfile.model_validate(p) for p in state["raw_employee_profiles"]]
    except ValidationError as e:
        logger.error("담당자 매핑 입력 검증 실패: %s", e)
        return {"error": f"INVALID_INPUT: {e}"}

    # LLM 호출 전, 후보를 코드로 먼저 추린다 (rule_filter.py 참고)
    candidates = filter_candidates(raw_profiles, state["tasks"], state["needed_roles"])

    member_profiles = []
    for profile in candidates:
        try:
            tags = extract_experience_tags(profile)
        except ValidationError as e:
            logger.error("담당자 매핑 스키마 검증 실패 (employee_id=%s): %s", profile.employee_id, e)
            return {"error": f"SCHEMA_VALIDATION_FAILED: {e}"}
        except Exception as e:
            logger.exception("담당자 매핑 실행 중 오류 (employee_id=%s)", profile.employee_id)
            return {"error": f"GENERATION_FAILED: {e}"}

        member_profiles.append(
            EmployeeFitnessProfile(
                employee_id=profile.employee_id,
                skills=profile.skills,  # 이미 구조화된 값 — 코드가 그대로 복사, LLM 관여 없음
                certifications=profile.certifications,  # 이미 구조화된 값 — 코드가 그대로 복사
                past_similar_tasks=tags.tags,  # LLM이 만든 값
            ).model_dump(mode="json")
        )

    return {"member_profiles": member_profiles, "error": None}

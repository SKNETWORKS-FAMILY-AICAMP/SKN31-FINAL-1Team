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
프로젝트 참여 여부를 어느 테이블/컬럼으로 판단할지는 아직 백엔드와 미확인 —
호출부가 그 필터링까지 끝낸 목록을 넘겨준다고 가정한다.
"""

import logging
from typing import Any, Dict, List

from pydantic import ValidationError

from shared.llm_client import create_structured
from shared.retry_config import DEFAULT_MAX_TOKENS, MAX_RETRIES, TEMPERATURE_STRUCTURED

from .prompt_builder import build_extraction_prompt
from .schemas import EmployeeFitnessProfile, ExtractedExperienceTags, RawEmployeeProfile

logger = logging.getLogger(__name__)


def extract_experience_tags(profile: RawEmployeeProfile) -> ExtractedExperienceTags:
    """career_history_text가 비어있으면 LLM 호출 없이 바로 빈 태그를 반환한다."""
    if not profile.career_history_text.strip():
        return ExtractedExperienceTags(tags=[])

    prompt = build_extraction_prompt(profile)
    return create_structured(
        system_prompt=prompt,
        user_message="위 경력기술서에서 경험 태그를 추출하라.",
        response_model=ExtractedExperienceTags,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=TEMPERATURE_STRUCTURED,
        max_retries=MAX_RETRIES,
    )


def assignee_mapping_node(state: Dict[str, Any]) -> Dict[str, Any]:
    if "raw_employee_profiles" not in state:
        return {"error": "MISSING_INPUT: state['raw_employee_profiles'] — 호출부가 미리 채워야 함"}

    try:
        raw_profiles = [RawEmployeeProfile.model_validate(p) for p in state["raw_employee_profiles"]]
    except ValidationError as e:
        logger.error("담당자 매핑 입력 검증 실패: %s", e)
        return {"error": f"INVALID_INPUT: {e}"}

    member_profiles = []
    for profile in raw_profiles:
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

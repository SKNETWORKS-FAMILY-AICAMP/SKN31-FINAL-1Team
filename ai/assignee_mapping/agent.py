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
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from shared.llm_client import create_structured
from shared.retry_config import DEFAULT_MAX_TOKENS, MAX_RETRIES, TEMPERATURE_STRUCTURED

from .prompt_builder import build_extraction_batch_prompt, build_extraction_prompt
from .rule_filter import filter_candidates
from .schemas import (
    EmployeeFitnessProfile,
    ExtractedExperienceTags,
    ExtractedExperienceTagsBatch,
    RawEmployeeProfile,
)

logger = logging.getLogger(__name__)

# 캐시에 없는 후보를 한 번의 LLM 호출에 몇 명씩 묶을지. career_history_text가
# 사람마다 꽤 길 수 있어 유닛 배치(REASON_BATCH_SIZE=8)보다는 살짝 낮춰 잡았다.
EXTRACTION_BATCH_SIZE = 10

# 프로세스 안에서 유지되는 경험 태그 캐시: career_history_text(원문) -> tags.
# 같은 사람의 경력기술서가 안 바뀐 채로 파이프라인이 다시 도는 경우(예: PM이
# 배정 미리보기를 여러 번 재실행하는 2단계 확정 흐름) 재호출을 건너뛴다.
# ai/는 여전히 DB를 모른다 — 프로세스 재시작 후에도 남기려면 호출부가
# state["known_experience_tags"]로 이전 결과를 넘겨주면 된다(assignee_mapping_node 참고).
_experience_tags_cache: Dict[str, List[str]] = {}


def _get_cached_tags(text: str) -> Optional[ExtractedExperienceTags]:
    if text in _experience_tags_cache:
        return ExtractedExperienceTags(tags=_experience_tags_cache[text])
    return None


def _store_tags(text: str, tags: ExtractedExperienceTags) -> None:
    _experience_tags_cache[text] = tags.tags


def extract_experience_tags(profile: RawEmployeeProfile) -> ExtractedExperienceTags:
    """career_history_text가 비어있으면 LLM 호출 없이 바로 빈 태그를 반환한다."""
    if not profile.career_history_text.strip():
        return ExtractedExperienceTags(tags=[])

    prompt = build_extraction_prompt(profile)
    tags = create_structured(
        system_prompt=prompt,
        user_message="위 경력기술서에서 경험 태그를 추출하라.",
        response_model=ExtractedExperienceTags,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=TEMPERATURE_STRUCTURED,
        max_retries=MAX_RETRIES,
    )
    _store_tags(profile.career_history_text, tags)
    return tags


def extract_experience_tags_batch(
    profiles: List[RawEmployeeProfile],
) -> Dict[str, ExtractedExperienceTags]:
    """
    캐시에 없는 후보 여러 명을 한 번의 LLM 호출로 처리한다. 반환값은
    employee_id -> ExtractedExperienceTags. 결과는 개인별 캐시에도 저장한다.
    """
    if not profiles:
        return {}

    prompt = build_extraction_batch_prompt(profiles)
    batch: ExtractedExperienceTagsBatch = create_structured(
        system_prompt=prompt,
        user_message="위 경력기술서들에서 각각 경험 태그를 추출하라.",
        response_model=ExtractedExperienceTagsBatch,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=TEMPERATURE_STRUCTURED,
        max_retries=MAX_RETRIES,
    )

    text_by_employee = {p.employee_id: p.career_history_text for p in profiles}
    result: Dict[str, ExtractedExperienceTags] = {}
    for item in batch.items:
        tags = ExtractedExperienceTags(tags=item.tags)
        result[item.employee_id] = tags
        text = text_by_employee.get(item.employee_id)
        if text:
            _store_tags(text, tags)
    return result


def assignee_mapping_node(state: Dict[str, Any]) -> Dict[str, Any]:
    missing = [k for k in ("raw_employee_profiles", "tasks", "needed_roles") if k not in state]
    if missing:
        return {"error": f"MISSING_INPUT: state{missing} — 호출부가 미리 채워야 함"}

    try:
        raw_profiles = [RawEmployeeProfile.model_validate(p) for p in state["raw_employee_profiles"]]
    except ValidationError as e:
        logger.error("담당자 매핑 입력 검증 실패: %s", e)
        return {"error": f"INVALID_INPUT: {e}"}

    # 호출부(백엔드)가 이전 실행에서 영속시켜 둔 태그가 있으면 캐시를 시드한다.
    # ai/는 여전히 DB를 모른다 — 이 값을 어떻게 저장/조회할지는 호출부 책임이고,
    # 여기서는 그냥 {career_history_text: [tags]} 형태의 평범한 dict로만 받는다.
    known_tags = state.get("known_experience_tags") or {}
    for text, tags in known_tags.items():
        if text not in _experience_tags_cache:
            _experience_tags_cache[text] = tags

    # LLM 호출 전, 후보를 코드로 먼저 추린다 (rule_filter.py 참고)
    candidates = filter_candidates(raw_profiles, state["tasks"], state["needed_roles"])

    tags_by_employee: Dict[str, ExtractedExperienceTags] = {}
    to_call: List[RawEmployeeProfile] = []
    for profile in candidates:
        text = profile.career_history_text.strip()
        if not text:
            tags_by_employee[profile.employee_id] = ExtractedExperienceTags(tags=[])
            continue
        cached = _get_cached_tags(text)
        if cached is not None:
            tags_by_employee[profile.employee_id] = cached
        else:
            to_call.append(profile)

    try:
        for i in range(0, len(to_call), EXTRACTION_BATCH_SIZE):
            batch_profiles = to_call[i : i + EXTRACTION_BATCH_SIZE]
            tags_by_employee.update(extract_experience_tags_batch(batch_profiles))
    except ValidationError as e:
        logger.error("담당자 매핑 스키마 검증 실패(배치): %s", e)
        return {"error": f"SCHEMA_VALIDATION_FAILED: {e}"}
    except Exception as e:
        logger.exception("담당자 매핑 실행 중 오류(배치)")
        return {"error": f"GENERATION_FAILED: {e}"}

    # 누락 방어: 배치 응답에 employee_id가 빠졌으면 그 사람만 단건으로 보완한다.
    for profile in to_call:
        if profile.employee_id in tags_by_employee:
            continue
        logger.warning("employee_id=%s: 배치 응답에 없어 단건 재호출", profile.employee_id)
        try:
            tags_by_employee[profile.employee_id] = extract_experience_tags(profile)
        except ValidationError as e:
            logger.error("담당자 매핑 스키마 검증 실패 (employee_id=%s): %s", profile.employee_id, e)
            return {"error": f"SCHEMA_VALIDATION_FAILED: {e}"}
        except Exception as e:
            logger.exception("담당자 매핑 실행 중 오류 (employee_id=%s)", profile.employee_id)
            return {"error": f"GENERATION_FAILED: {e}"}

    member_profiles = []
    for profile in candidates:
        tags = tags_by_employee[profile.employee_id]
        member_profiles.append(
            EmployeeFitnessProfile(
                employee_id=profile.employee_id,
                skills=profile.skills,  # 이미 구조화된 값 — 코드가 그대로 복사, LLM 관여 없음
                certifications=profile.certifications,  # 이미 구조화된 값 — 코드가 그대로 복사
                past_similar_tasks=tags.tags,  # LLM이 만든 값
            ).model_dump(mode="json")
        )

    return {"member_profiles": member_profiles, "error": None}

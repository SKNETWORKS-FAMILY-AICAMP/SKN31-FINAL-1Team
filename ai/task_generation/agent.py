"""
a2_2_task_generation/agent.py

업무 자동 생성 (FR-05-014, 015)

업무 개수는 요구사항 1건당 최소 1개~최대 3개로 생성한다(프로젝트 전체를
묶어 고정 개수로 세지 않는다 — 요구사항이 많을 때 일부가 업무 없이 누락되는
문제가 실제로 있었다, 2026-09-02 확인). 실제 참여 인원 수와는 무관하게
요구사항 내용만 보고 정한다 — "몇 명이 필요한지"는 이 단계가 아니라
`team_sizing.py`가 이 출력(estimated_hours)을 가지고 별도로 추정한다.

요구사항 커버리지는 다음 순서로 처리한다(2026-09-03):
  1. 요구사항 ID를 키로 하는 느슨한 Dict 스키마(TaskByRequirement)로 전체
     요구사항을 한 번에 요청한다. 문서를 미리 여러 조각으로 쪼개 나눠
     호출하지 않는다 — 항상 통째로 한 번 시도한다.
  2. 결과에서 빠진 요구사항 ID를 코드로 계산한다.
  3. 빠진 게 있으면, 그 ID들만 필수로 건 좁은 스키마
     (schemas.build_requirement_keyed_model)로 다시 요청하고 기존 결과에
     병합한다 — 이미 성공한 부분은 다시 만들지 않고, 실패(누락)한 부분만
     다시 묻는다.
  4. 재시도 횟수를 다 써도 남으면 로그로 남기고 있는 그대로 반환한다.

여러 번의 LLM 호출(1차 + 재시도)이 섞이면 TASK-*/EPIC-*/SUBTASK-* ID가
호출마다 다시 TASK-001부터 매겨져 충돌할 수 있어, 마지막에 _renumber()가
전체를 한 번에 재번호 매긴다. ID 유일성은 LLM이 아니라 이 코드가 보장한다.
"""

import logging
from typing import Any, Dict, List, Set

from pydantic import ValidationError

from shared.llm_client import create_structured
from shared.retry_config import DEFAULT_MAX_TOKENS, MAX_RETRIES, TEMPERATURE_STRUCTURED

from .prompt_builder import build_system_prompt
from .schemas import TaskByRequirement, TaskItem, TaskList, build_requirement_keyed_model

logger = logging.getLogger(__name__)


def _extract(by_requirement: Dict[str, List[TaskItem]]) -> List[TaskItem]:
    flat: List[TaskItem] = []
    for req_id, items in by_requirement.items():
        for task in items:
            # source_req_id는 LLM이 채운 값을 신뢰하지 않고, 이 값이 나온
            # 키(req_id)로 코드가 직접 덮어쓴다 — 구조 자체가 이미 정답을
            # 알고 있으니, LLM이 이 필드를 잘못 채울 여지를 없앤다.
            task.source_req_id = req_id
            flat.append(task)
    return flat


def _missing_ids(req_ids: List[str], groups: List[List[TaskItem]]) -> Set[str]:
    covered = {t.source_req_id for group in groups for t in group}
    return set(req_ids) - covered


def _renumber(groups: List[List[TaskItem]]) -> List[TaskItem]:
    """여러 번의 LLM 호출(1차 + 재시도) 결과를 합칠 때, 호출마다 다시
    TASK-001부터 매겨진 ID가 충돌하는 걸 정리한다.

    같은 호출 안에서 재사용된 epic_id는 같은 새 Epic으로 묶되, 호출이
    다르면 원본 epic_id가 같아도 별개의 Epic으로 취급한다 — 각 호출이
    서로의 존재를 모른 채 독립적으로 생성했기 때문에, 우연히 겹친 ID를
    같은 Epic으로 오인하면 안 된다. 재시도가 없어 호출이 1번뿐이면
    사실상 순번만 다시 매기는 것과 같다.
    """
    renumbered: List[TaskItem] = []
    task_counter = 0
    epic_counter = 0
    for group in groups:
        epic_id_map: Dict[str, str] = {}  # 이 호출 안에서만 유효
        for task in group:
            if task.epic_id not in epic_id_map:
                epic_counter += 1
                epic_id_map[task.epic_id] = f"EPIC-{epic_counter:03d}"
            task_counter += 1
            task.task_id = f"TASK-{task_counter:03d}"
            task.epic_id = epic_id_map[task.epic_id]
            for sub_idx, sub in enumerate(task.subtasks, start=1):
                sub.subtask_id = f"SUBTASK-{task_counter:03d}-{sub_idx}"
            renumbered.append(task)
    return renumbered


def generate_tasks(requirement_doc: dict) -> List[TaskItem]:
    system_prompt = build_system_prompt(requirement_doc)
    req_ids = [r["id"] for r in requirement_doc.get("requirements", [])]
    user_message = "위 요구사항정의서를 바탕으로 업무를 생성하라."

    result = create_structured(
        system_prompt=system_prompt,
        user_message=user_message,
        response_model=TaskByRequirement,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=TEMPERATURE_STRUCTURED,
        max_retries=MAX_RETRIES,
    )
    groups: List[List[TaskItem]] = [_extract(result.by_requirement)]

    for attempt in range(MAX_RETRIES):
        missing = _missing_ids(req_ids, groups)
        if not missing:
            break
        logger.warning(
            "업무 생성 결과가 요구사항 %d건을 못 커버함(재시도 %d/%d): %s",
            len(missing), attempt + 1, MAX_RETRIES, sorted(missing),
        )
        retry_model = build_requirement_keyed_model(sorted(missing))
        retry_message = (
            f"{user_message}\n\n"
            f"방금 생성한 결과가 다음 요구사항 ID를 하나도 커버하지 못했다: "
            f"{sorted(missing)}. 이 요구사항 ID들 각각을 키로 하여, 해당 요구사항에서 "
            f"파생된 업무를 최소 1개 이상 담아라."
        )
        try:
            retry_result = create_structured(
                system_prompt=system_prompt,
                user_message=retry_message,
                response_model=retry_model,
                max_tokens=DEFAULT_MAX_TOKENS,
                temperature=TEMPERATURE_STRUCTURED,
                max_retries=MAX_RETRIES,
            )
        except Exception as e:
            logger.warning("재시도 호출 실패(재시도 %d/%d): %s", attempt + 1, MAX_RETRIES, e)
            continue
        new_group: List[TaskItem] = []
        for req_id in sorted(missing):
            for task in getattr(retry_result, req_id):
                # 여기서도 source_req_id는 LLM 값이 아니라 키로 확정한다.
                task.source_req_id = req_id
                new_group.append(task)
        groups.append(new_group)

    remaining = _missing_ids(req_ids, groups)
    if remaining:
        logger.error("재시도 소진 — 요구사항 %d건 여전히 업무 없음: %s", len(remaining), sorted(remaining))

    merged = _renumber(groups)
    # 전부 실패해서 결과가 비어 있으면 TaskList의 min_length=1 검증에
    # 걸려 ValidationError로 올라간다 — task_generation_node가 이를 잡아
    # {"error": ...}로 정리한다.
    return TaskList(tasks=merged).tasks


def task_generation_node(state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        result = generate_tasks(state["requirement_doc"])
    except ValidationError as e:
        logger.error("A2-2 스키마 검증 실패: %s", e)
        return {"error": f"SCHEMA_VALIDATION_FAILED: {e}"}
    except Exception as e:
        logger.exception("A2-2 실행 중 오류")
        return {"error": f"GENERATION_FAILED: {e}"}

    return {"tasks": [t.model_dump(mode="json") for t in result], "error": None}

"""
노드 2 기획서 생성 프롬프트 연결 모듈.

실제 프롬프트 규칙과 퓨샷 예시는 다음 YAML 파일에서 관리합니다.

생성 규칙:
    prompt_templates/plan_generation.yaml

퓨샷 예시:
    prompt_templates/plan_generation_fewshots.yaml

YAML 읽기와 검증:
    prompt_loader.py

이 파일은 agent.py에서 사용하는 공개 이름을 유지하고,
구조화 JSON을 실제 LLM 입력 메시지로 조립합니다.
"""

import json

from .list_builder import build_feature_citation_sources, build_user_citation_sources
from .prompt_loader import (
    build_plan_fewshot_messages,
    build_plan_system_prompt,
    build_regenerate_prompt,
)


# 기존 agent.py가 import하는 이름을 유지합니다.
#
# 용어집이 없는 기본 시스템 프롬프트입니다.
SYSTEM_PROMPT = build_plan_system_prompt()

# 기존 agent.py가 서술형 섹션 재생성 시 사용하는 이름입니다.
REGENERATE_PROMPT = build_regenerate_prompt()


def build_system_prompt(
    glossary_text: str = "",
) -> str:
    """
    기획서 생성용 시스템 프롬프트를 반환합니다.

    용어집이 없으면 기본 규칙만 반환합니다.
    용어집이 있으면 용어집 사용 규칙과 실제 용어집 내용을
    시스템 프롬프트에 추가합니다.
    """
    return build_plan_system_prompt(
        glossary_text=glossary_text,
    )


def _verified_only(items) -> list:
    """evidence_status가 verified인 항목만 남깁니다."""
    return [
        item
        for item in (items or [])
        if isinstance(item, dict)
        and item.get("evidence_status") == "verified"
    ]


def _build_generation_payload(
    structured: dict,
) -> dict:
    """
    노드 1의 전체 구조화 결과 중 서술형 작성에 필요한 필드만 고릅니다.

    노드 2의 LLM 담당 범위:
        프로젝트 개요
        핵심 목표
        대상 사용자
        세부 목표 및 문제 정의
        주요 기능

    기술 및 제약사항과 최종 결정사항은 list_builder.py에서 검증된
    구조화 데이터를 사용해 코드로 조립합니다(그대로 유지).

    2026-09-15: requirements.functional과 decisions[feature]를 이제
    같이 전달합니다 — 5번(주요 기능)을 LLM이 직접 묶어 쓰도록 바꿨기
    때문입니다(plan_draft/schemas.py PlanSections.features 참고).

    다만 이 필드는 features 작성에만 씁니다 — overview·problem·users
    작성 규칙(plan_generation.yaml)에서 여전히 이 필드를 근거로 쓰지
    말라고 명시합니다. 문제와 기능 사이의 인과관계를 서술형 섹션이
    임의로 만드는 걸 막기 위한 원래 우려는 그대로 유효합니다.

    2026-09-16: verified만 걸러 넘기던 걸(_verified_only) 그만뒀습니다.
    그러면 노드①의 근거 검증이 한두 글자 오차로 실패한 진짜 기능
    요구사항이 LLM한테 보여지지도 못하고 조용히 사라집니다(6·7번에서
    이미 확인된 것과 같은 침묵 실패). 이제 verified 여부와 무관하게
    번호만 매겨(build_feature_citation_sources) 전부 넘기되, 검증
    상태(evidence_status)는 프롬프트에서 지웁니다 — LLM이 "안전한"
    번호만 골라 인용하는 걸 막기 위해서입니다. Feature.source_indices로
    LLM이 어떤 번호를 참고했는지 답하면, agent.py가 그 번호들의 실제
    검증 상태를 코드로 확인해 표시 여부를 결정합니다.
    """
    if not isinstance(structured, dict):
        raise TypeError(
            "structured는 딕셔너리여야 합니다."
        )

    project = structured.get("project") or {}

    feature_sources = [
        {
            "index": item["index"],
            "content": item["content"],
            "review_context": item.get("context_flag") or "",
        }
        for item in build_feature_citation_sources(structured)
    ]

    return {
        "meeting_source_text": structured.get("plan_source_text") or "",
        "validation_notes": structured.get("validation_notes") or [],
        "project": project,
        # 회의록 구조화 단계가 프로젝트의 주목적을 별도 신호로 잡은 경우
        # project.problem만 보여주면 구현 화제에 밀려 핵심 목표에서 누락될
        # 수 있습니다. 검증된 목적 신호를 problem 전용 근거로 명시합니다.
        "service_purpose_signals": [
            item for item in (structured.get("user_signals") or [])
            if isinstance(item, dict)
            and item.get("kind") == "service_purpose"
            and item.get("statement_status") == "stated"
            and item.get("evidence_status") == "verified"
        ],
        "users": (
            structured.get("users")
            or []
        ),
        "feature_sources_for_citation": feature_sources,
        # 2026-09-16: DetailedGoal.matched_goal_index가 참조할 번호 매긴
        # 목표 목록입니다. project.goals를 그대로 보여주면 LLM이 배열
        # 순서를 스스로 세야 해서 번호를 잘못 셀 위험이 있어, 코드가
        # 직접 번호를 매겨 넘깁니다. verified 근거가 있는 목표만
        # 인용 대상으로 노출합니다 — 검증 안 된 목표를 인용하게 하면
        # "회의 기반"이라는 라벨의 신뢰가 애초에 성립하지 않습니다.
        "goals_for_citation": [
            {"index": i, "content": g.get("content", "")}
            for i, g in enumerate(_verified_only(project.get("goals")))
        ],
        # 2026-09-17: matched_goal_index와 같은 이유로 problem 쪽에도
        # 번호 매긴 인용 대상을 추가합니다(DetailedGoal.matched_problem_index
        # 참고) — quote 완전 일치로는 LLM이 옮겨 적은 problem 문장이 어떤
        # problem_item과 대응하는지 코드가 확인할 수 없어, 그 항목의
        # context_flag(사실 검토 경고)를 이어 붙일 근거가 없었습니다.
        "problem_sources_for_citation": [
            {"index": i, "content": p.get("content", "")}
            for i, p in enumerate(_verified_only(project.get("problem_items")))
        ],
        # 2026-09-17: 4번 대상 사용자 설명을 보완할 때 참고할 검증된
        # 기능·데이터 후보입니다(list_builder.build_user_citation_sources
        # 참고). users 배열에 이미 있는 사용자와 명백히 관련된 내용만
        # 골라 쓰고, 새 사용자 유형을 만드는 데는 쓰지 않습니다.
        "user_sources_for_citation": [
            dict(item)
            for item in build_user_citation_sources(structured)
        ],
    }


def build_messages(
    structured: dict,
    glossary_text: str = "",
) -> list[dict]:
    """
    최초 기획서 생성용 메시지를 만듭니다.

    메시지 구성:
        일반 퓨샷 입력
        일반 퓨샷 출력
        일반 퓨샷 입력
        일반 퓨샷 출력
        용어집 퓨샷 입력과 출력
        실제 구조화 JSON

    용어집 퓨샷은 glossary_text가 있을 때만 포함합니다.
    """
    payload = _build_generation_payload(
        structured
    )

    messages = build_plan_fewshot_messages(
        glossary_text=glossary_text,
    )

    messages.append(
        {
            "role": "user",
            "content": json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
        }
    )

    return messages


def build_regenerate_messages(
    structured: dict,
    section_key: str,
    reject_type: str,
    comment: str,
) -> list[dict]:
    """
    서술형 섹션 하나를 재생성하기 위한 메시지를 만듭니다.

    기존 agent.py의 호출 형식을 유지합니다.

    재생성 가능한 대상은 agent.py에서 제한합니다.
    이 함수는 전달받은 원본 구조화 JSON과 반려 정보를
    LLM 입력 JSON으로 조립하는 역할만 담당합니다.
    """
    if not isinstance(structured, dict):
        raise TypeError(
            "structured는 딕셔너리여야 합니다."
        )

    if not isinstance(section_key, str):
        raise TypeError(
            "section_key는 문자열이어야 합니다."
        )

    if not isinstance(reject_type, str):
        raise TypeError(
            "reject_type은 문자열이어야 합니다."
        )

    if not isinstance(comment, str):
        raise TypeError(
            "comment는 문자열이어야 합니다."
        )

    payload = {
        "structured": _build_generation_payload(
            structured
        ),
        "section_key": section_key.strip(),
        "reject_type": reject_type.strip(),
        "comment": comment.strip(),
    }

    return [
        {
            "role": "user",
            "content": json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
        }
    ]

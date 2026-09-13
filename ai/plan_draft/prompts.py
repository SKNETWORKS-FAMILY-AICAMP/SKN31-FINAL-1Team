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

    주요 기능, 기술 및 제약사항과 최종 결정사항은 list_builder.py에서
    검증된 구조화 데이터를 사용해 코드로 조립합니다.

    기능 요구사항과 결정사항을 서술형 LLM에 전달하지 않습니다.
    문제와 기능 사이의 관계가 구조화되어 있지 않은 상태에서 두 목록을
    함께 전달하면, 모델이 그럴듯한 인과관계를 임의로 만들 수 있기 때문입니다.
    세부 목표는 project.problem_items와 project.goals만 사용합니다.
    """
    if not isinstance(structured, dict):
        raise TypeError(
            "structured는 딕셔너리여야 합니다."
        )

    return {
        "project": (
            structured.get("project")
            or {}
        ),
        "users": (
            structured.get("users")
            or []
        ),
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

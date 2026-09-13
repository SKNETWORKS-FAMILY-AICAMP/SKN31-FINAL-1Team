"""
노드 2 기획서 생성 프롬프트 YAML 로더.

프롬프트의 실제 규칙과 퓨샷 예시는 Python 코드가 아니라
다음 YAML 파일에서 관리합니다.

규칙:
    prompt_templates/plan_generation.yaml

퓨샷 예시:
    prompt_templates/plan_generation_fewshots.yaml

이 모듈의 역할:
    1. YAML 파일을 읽습니다.
    2. 필수 항목과 자료형을 검증합니다.
    3. 퓨샷 출력이 PlanSections 스키마와 일치하는지 검증합니다.
    4. YAML 규칙을 시스템 프롬프트로 변환합니다.
    5. 퓨샷 예시를 LLM 메시지 배열로 변환합니다.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .schemas import PlanSections


# 현재 파일이 있는 plan_draft 디렉터리를 기준으로
# prompt_templates 디렉터리의 절대 경로를 계산합니다.
TEMPLATE_DIRECTORY = (
    Path(__file__).resolve().parent
    / "prompt_templates"
)

# 최초 기획서 생성 규칙 파일입니다.
PLAN_TEMPLATE_PATH = (
    TEMPLATE_DIRECTORY
    / "plan_generation.yaml"
)

# 최초 기획서 생성 퓨샷 예시 파일입니다.
PLAN_FEWSHOTS_PATH = (
    TEMPLATE_DIRECTORY
    / "plan_generation_fewshots.yaml"
)


class PromptTemplateError(ValueError):
    """
    프롬프트 YAML 파일이나 내부 구조가 잘못됐을 때 발생하는 오류입니다.

    일반 ValueError 대신 별도 오류를 사용하면 로그에서
    프롬프트 설정 문제인지 쉽게 구분할 수 있습니다.
    """


def _load_yaml(path: Path) -> dict:
    """
    YAML 파일을 읽습니다.

    확인하는 내용:
        파일이 실제로 존재하는지
        YAML 문법이 올바른지
        최상위 자료형이 객체인지
    """
    if not path.exists():
        raise PromptTemplateError(
            f"프롬프트 파일을 찾을 수 없습니다: {path}"
        )

    try:
        loaded = yaml.safe_load(
            path.read_text(encoding="utf-8")
        )
    except yaml.YAMLError as error:
        raise PromptTemplateError(
            f"프롬프트 YAML 문법이 올바르지 않습니다: {path}"
        ) from error

    if not isinstance(loaded, dict):
        raise PromptTemplateError(
            f"프롬프트 YAML은 객체여야 합니다: {path}"
        )

    return loaded


def _require_mapping(
    data: dict,
    key: str,
    source_name: str,
) -> dict:
    """
    지정한 필드가 YAML 객체인지 확인합니다.

    YAML에서 다음 형태가 객체입니다.

    problem_rules:
      preferred_sources:
        - project.problem_items
      rules:
        - 문제를 한 문장으로 작성합니다.
    """
    value = data.get(key)

    if not isinstance(value, dict):
        raise PromptTemplateError(
            f"{source_name}.{key}는 객체여야 합니다."
        )

    return value


def _require_list(
    data: dict,
    key: str,
    source_name: str,
) -> list:
    """
    지정한 필드가 YAML 배열인지 확인합니다.

    YAML에서 다음 형태가 배열입니다.

    title_rules:
      - 제목은 30자 이내로 작성합니다.
      - 제목 앞에 번호를 넣지 않습니다.
    """
    value = data.get(key)

    if not isinstance(value, list):
        raise PromptTemplateError(
            f"{source_name}.{key}는 배열이어야 합니다."
        )

    return value


def _require_text(
    data: dict,
    key: str,
    source_name: str,
) -> str:
    """
    지정한 필드가 비어 있지 않은 문자열인지 확인합니다.
    """
    value = data.get(key)

    if not isinstance(value, str) or not value.strip():
        raise PromptTemplateError(
            f"{source_name}.{key}는 "
            "비어 있지 않은 문자열이어야 합니다."
        )

    return value.strip()


def _validate_plan_template(template: dict) -> None:
    """
    plan_generation.yaml의 필수 구조를 검증합니다.

    이 검증은 YAML 문법뿐 아니라 현재 Python 스키마와
    관리 규칙이 서로 맞는지도 확인합니다.
    """
    metadata = _require_mapping(
        template,
        "metadata",
        "plan_generation",
    )

    version = _require_text(
        metadata,
        "version",
        "plan_generation.metadata",
    )

    if version != "2.2":
        raise PromptTemplateError(
            "plan_generation.yaml 버전은 2.2여야 합니다."
        )

    _require_text(
        template,
        "role",
        "plan_generation",
    )

    # 최상위 출력 구조를 검증합니다.
    output_contract = _require_mapping(
        template,
        "output_contract",
        "plan_generation",
    )

    root_fields = _require_list(
        output_contract,
        "root_fields",
        "plan_generation.output_contract",
    )

    expected_root_fields = [
        "sections",
        "goals",
    ]

    if root_fields != expected_root_fields:
        raise PromptTemplateError(
            "output_contract.root_fields는 "
            "sections, goals 순서여야 합니다."
        )

    # LLM이 sections 배열에 생성할 서술형 섹션을 검증합니다.
    narrative_sections = _require_list(
        output_contract,
        "narrative_sections",
        "plan_generation.output_contract",
    )

    narrative_keys: list[str] = []

    for index, item in enumerate(narrative_sections):
        if not isinstance(item, dict):
            raise PromptTemplateError(
                "output_contract.narrative_sections의 "
                f"{index}번 항목은 객체여야 합니다."
            )

        key = _require_text(
            item,
            "key",
            (
                "plan_generation.output_contract."
                f"narrative_sections[{index}]"
            ),
        )

        _require_text(
            item,
            "title",
            (
                "plan_generation.output_contract."
                f"narrative_sections[{index}]"
            ),
        )

        narrative_keys.append(key)

    expected_narrative_keys = [
        "overview",
        "problem",
        "users",
    ]

    if narrative_keys != expected_narrative_keys:
        raise PromptTemplateError(
            "서술형 섹션은 overview, problem, users "
            "순서여야 합니다."
        )

    _require_list(
        template,
        "common_rules",
        "plan_generation",
    )

    # overview, problem, users 작성 규칙을 검증합니다.
    section_rules = _require_mapping(
        template,
        "section_rules",
        "plan_generation",
    )

    for section_key in expected_narrative_keys:
        section_rule = _require_mapping(
            section_rules,
            section_key,
            "plan_generation.section_rules",
        )

        section_source_name = (
            "plan_generation.section_rules."
            f"{section_key}"
        )

        _require_text(
            section_rule,
            "title",
            section_source_name,
        )

        _require_text(
            section_rule,
            "output_key",
            section_source_name,
        )

        _require_list(
            section_rule,
            "source_fields",
            section_source_name,
        )

        _require_list(
            section_rule,
            "rules",
            section_source_name,
        )

    # 세부 목표 및 문제 정의 규칙을 검증합니다.
    detailed_goal_rules = _require_mapping(
        template,
        "detailed_goal_rules",
        "plan_generation",
    )

    detailed_goal_source = (
        "plan_generation.detailed_goal_rules"
    )

    _require_text(
        detailed_goal_rules,
        "title",
        detailed_goal_source,
    )

    _require_text(
        detailed_goal_rules,
        "output_field",
        detailed_goal_source,
    )

    _require_list(
        detailed_goal_rules,
        "source_fields",
        detailed_goal_source,
    )

    item_fields = _require_list(
        detailed_goal_rules,
        "item_fields",
        detailed_goal_source,
    )

    # DetailedGoal Pydantic 모델과 같은 필드인지 확인합니다.
    expected_item_fields = [
        "title",
        "problem",
        "goal",
        "problem_evidence",
        "goal_evidence",
    ]

    if item_fields != expected_item_fields:
        raise PromptTemplateError(
            "detailed_goal_rules.item_fields가 "
            "DetailedGoal 스키마와 일치하지 않습니다."
        )

    _require_mapping(
        detailed_goal_rules,
        "count",
        detailed_goal_source,
    )

    _require_list(
        detailed_goal_rules,
        "rules",
        detailed_goal_source,
    )

    # title_rules는 규칙 문장들이 나열된 배열입니다.
    _require_list(
        detailed_goal_rules,
        "title_rules",
        detailed_goal_source,
    )

    # problem_rules와 goal_rules는 각각
    # preferred_sources와 rules를 포함하는 객체입니다.
    for rule_group_key in [
        "problem_rules",
        "goal_rules",
    ]:
        rule_group = _require_mapping(
            detailed_goal_rules,
            rule_group_key,
            detailed_goal_source,
        )

        rule_group_source = (
            f"{detailed_goal_source}."
            f"{rule_group_key}"
        )

        _require_list(
            rule_group,
            "preferred_sources",
            rule_group_source,
        )

        _require_list(
            rule_group,
            "rules",
            rule_group_source,
        )

    # evidence_rules는 근거 규칙 문장들의 배열입니다.
    _require_list(
        detailed_goal_rules,
        "evidence_rules",
        detailed_goal_source,
    )

    # 용어집 규칙을 검증합니다.
    glossary_rules = _require_mapping(
        template,
        "glossary_rules",
        "plan_generation",
    )

    _require_list(
        glossary_rules,
        "rules",
        "plan_generation.glossary_rules",
    )

    # 섹션 재생성 규칙을 검증합니다.
    regeneration_rules = _require_mapping(
        template,
        "regeneration_rules",
        "plan_generation",
    )

    _require_list(
        regeneration_rules,
        "input_fields",
        "plan_generation.regeneration_rules",
    )

    _require_list(
        regeneration_rules,
        "rules",
        "plan_generation.regeneration_rules",
    )


def _validate_example(
    example: Any,
    group_name: str,
    index: int,
) -> None:
    """
    퓨샷 예시 하나를 검증합니다.

    input은 구조화 JSON 객체여야 하고,
    output은 PlanSections 스키마를 통과해야 합니다.
    """
    source_name = (
        "plan_generation_fewshots."
        f"{group_name}[{index}]"
    )

    if not isinstance(example, dict):
        raise PromptTemplateError(
            f"{source_name}는 객체여야 합니다."
        )

    _require_text(
        example,
        "id",
        source_name,
    )

    input_data = example.get("input")
    output_data = example.get("output")

    if not isinstance(input_data, dict):
        raise PromptTemplateError(
            f"{source_name}.input은 객체여야 합니다."
        )

    if not isinstance(output_data, dict):
        raise PromptTemplateError(
            f"{source_name}.output은 객체여야 합니다."
        )

    # 퓨샷 출력이 실제 Instructor response_model과
    # 일치하는지 실행 전에 확인합니다.
    try:
        PlanSections.model_validate(output_data)
    except Exception as error:
        raise PromptTemplateError(
            f"{source_name}.output이 "
            "PlanSections 스키마와 일치하지 않습니다."
        ) from error

    # 용어집 전용 예시는 glossary 필드도 필요합니다.
    if group_name == "glossary_examples":
        _require_text(
            example,
            "glossary",
            source_name,
        )


def _validate_fewshots_template(template: dict) -> None:
    """
    plan_generation_fewshots.yaml 전체를 검증합니다.
    """
    metadata = _require_mapping(
        template,
        "metadata",
        "plan_generation_fewshots",
    )

    version = _require_text(
        metadata,
        "version",
        "plan_generation_fewshots.metadata",
    )

    if version != "2.2":
        raise PromptTemplateError(
            "plan_generation_fewshots.yaml 버전은 "
            "2.2여야 합니다."
        )

    examples = _require_list(
        template,
        "examples",
        "plan_generation_fewshots",
    )

    glossary_examples = _require_list(
        template,
        "glossary_examples",
        "plan_generation_fewshots",
    )

    if not examples:
        raise PromptTemplateError(
            "일반 퓨샷 예시가 하나 이상 필요합니다."
        )

    # 일반 퓨샷 예시를 하나씩 검증합니다.
    for index, example in enumerate(examples):
        _validate_example(
            example,
            "examples",
            index,
        )

    # 용어집 퓨샷 예시를 하나씩 검증합니다.
    for index, example in enumerate(glossary_examples):
        _validate_example(
            example,
            "glossary_examples",
            index,
        )


@lru_cache(maxsize=1)
def load_plan_template() -> dict:
    """
    기획서 생성 규칙을 읽고 검증한 뒤 반환합니다.

    같은 프로세스에서 YAML을 매번 다시 읽지 않도록
    결과를 메모리에 캐시합니다.
    """
    template = _load_yaml(PLAN_TEMPLATE_PATH)
    _validate_plan_template(template)
    return template


@lru_cache(maxsize=1)
def load_plan_fewshots() -> dict:
    """
    기획서 퓨샷 예시를 읽고 검증한 뒤 반환합니다.
    """
    template = _load_yaml(PLAN_FEWSHOTS_PATH)
    _validate_fewshots_template(template)
    return template


def _render_structure(
    value: Any,
    indent: int = 0,
) -> list[str]:
    """
    YAML의 객체와 배열을 프롬프트용 일반 텍스트로 변환합니다.

    YAML 파일은 관리하기 좋은 구조를 유지하고,
    LLM에는 읽기 쉬운 들여쓰기 형식으로 전달합니다.
    """
    prefix = " " * indent
    lines: list[str] = []

    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(
                    _render_structure(
                        item,
                        indent + 2,
                    )
                )
            else:
                lines.append(
                    f"{prefix}{key}: {item}"
                )

        return lines

    if isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.extend(
                    _render_structure(
                        item,
                        indent + 2,
                    )
                )
            else:
                lines.append(f"{prefix}- {item}")

        return lines

    lines.append(f"{prefix}{value}")
    return lines


def _render_section(
    title: str,
    value: Any,
) -> str:
    """
    프롬프트의 제목과 구조화된 규칙 내용을 합칩니다.
    """
    lines = [title]
    lines.extend(_render_structure(value))
    return "\n".join(lines)


def build_plan_system_prompt(
    glossary_text: str = "",
) -> str:
    """
    최초 기획서 생성용 시스템 프롬프트를 만듭니다.

    용어집이 없으면 일반 생성 규칙만 포함합니다.
    용어집이 있으면 용어집 사용 규칙과 실제 용어집을 추가합니다.
    """
    template = load_plan_template()

    parts = [
        template["role"].strip(),
        _render_section(
            "출력 구조",
            template["output_contract"],
        ),
        _render_section(
            "공통 규칙",
            template["common_rules"],
        ),
        _render_section(
            "서술형 섹션 작성 규칙",
            template["section_rules"],
        ),
        _render_section(
            "세부 목표 및 문제 정의 작성 규칙",
            template["detailed_goal_rules"],
        ),
    ]

    if glossary_text.strip():
        parts.extend(
            [
                _render_section(
                    "용어집 사용 규칙",
                    template["glossary_rules"],
                ),
                (
                    "사내 용어집\n"
                    f"{glossary_text.strip()}"
                ),
            ]
        )

    return "\n\n".join(parts)


def build_regenerate_prompt() -> str:
    """
    서술형 섹션 하나를 다시 작성할 때 사용할 규칙을 만듭니다.
    """
    template = load_plan_template()

    return _render_section(
        "서술형 섹션 재생성 규칙",
        template["regeneration_rules"],
    )


def _json_text(value: dict) -> str:
    """
    딕셔너리를 한글이 유지되는 JSON 문자열로 변환합니다.
    """
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
    )


def build_plan_fewshot_messages(
    glossary_text: str = "",
) -> list[dict]:
    """
    기획서 생성 퓨샷 메시지를 만듭니다.

    일반 예시는 항상 포함합니다.
    용어집 예시는 실제 용어집이 제공된 경우에만 포함합니다.
    """
    template = load_plan_fewshots()
    messages: list[dict] = []

    # 일반 기획서 생성 예시를 추가합니다.
    for example in template["examples"]:
        messages.extend(
            [
                {
                    "role": "user",
                    "content": _json_text(
                        example["input"]
                    ),
                },
                {
                    "role": "assistant",
                    "content": _json_text(
                        example["output"]
                    ),
                },
            ]
        )

    # 실제 호출에 용어집이 있을 때만
    # 용어집 적용 예시를 메시지에 추가합니다.
    if glossary_text.strip():
        for example in template["glossary_examples"]:
            user_content = "\n\n".join(
                [
                    (
                        "사내 용어집\n"
                        f"{example['glossary'].strip()}"
                    ),
                    (
                        "구조화 JSON\n"
                        f"{_json_text(example['input'])}"
                    ),
                ]
            )

            messages.extend(
                [
                    {
                        "role": "user",
                        "content": user_content,
                    },
                    {
                        "role": "assistant",
                        "content": _json_text(
                            example["output"]
                        ),
                    },
                ]
            )

    return messages

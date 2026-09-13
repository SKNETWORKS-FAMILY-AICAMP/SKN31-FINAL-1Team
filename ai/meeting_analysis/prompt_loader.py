"""회의록 구조화 프롬프트 YAML 로더."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .schemas import MeetingExtraction


TEMPLATE_DIRECTORY = (
    Path(__file__).resolve().parent
    / "prompt_templates"
)

EXTRACTION_TEMPLATE_PATH = (
    TEMPLATE_DIRECTORY
    / "extraction.yaml"
)

EXTRACTION_FEWSHOTS_PATH = (
    TEMPLATE_DIRECTORY
    / "extraction_fewshots.yaml"
)


class PromptTemplateError(ValueError):
    """프롬프트 템플릿의 구조가 올바르지 않은 경우."""


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PromptTemplateError(
            f"프롬프트 파일을 찾을 수 없습니다: {path}"
        )

    text = path.read_text(encoding="utf-8")

    if not text.strip():
        raise PromptTemplateError(
            f"프롬프트 파일이 비어 있습니다: {path}"
        )

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise PromptTemplateError(
            f"프롬프트 YAML 형식이 올바르지 않습니다: {path}"
        ) from error

    if not isinstance(data, dict):
        raise PromptTemplateError(
            f"프롬프트 YAML의 최상위 값은 객체여야 합니다: {path}"
        )

    return data


def _require_mapping(
    data: dict[str, Any],
    key: str,
    context: str,
) -> dict[str, Any]:
    value = data.get(key)

    if not isinstance(value, dict):
        raise PromptTemplateError(
            f"{context}.{key}는 객체여야 합니다."
        )

    return value


def _require_list(
    data: dict[str, Any],
    key: str,
    context: str,
) -> list[Any]:
    value = data.get(key)

    if not isinstance(value, list):
        raise PromptTemplateError(
            f"{context}.{key}는 배열이어야 합니다."
        )

    return value


def _require_text(
    data: dict[str, Any],
    key: str,
    context: str,
) -> str:
    value = data.get(key)

    if not isinstance(value, str) or not value.strip():
        raise PromptTemplateError(
            f"{context}.{key}는 비어 있지 않은 문자열이어야 합니다."
        )

    return value.strip()


def _validate_extraction_template(
    template: dict[str, Any],
) -> None:
    metadata = _require_mapping(
        template,
        "metadata",
        "extraction",
    )

    _require_text(
        metadata,
        "version",
        "extraction.metadata",
    )

    _require_text(
        template,
        "role",
        "extraction",
    )

    absolute_rules = _require_list(
        template,
        "absolute_rules",
        "extraction",
    )

    if not absolute_rules:
        raise PromptTemplateError(
            "extraction.absolute_rules는 비어 있을 수 없습니다."
        )

    for index, rule in enumerate(absolute_rules):
        if not isinstance(rule, dict):
            raise PromptTemplateError(
                "extraction.absolute_rules의 각 항목은 객체여야 합니다."
            )

        _require_text(
            rule,
            "id",
            f"extraction.absolute_rules[{index}]",
        )

        _require_text(
            rule,
            "text",
            f"extraction.absolute_rules[{index}]",
        )

    project_rules = _require_mapping(
        template,
        "project_rules",
        "extraction",
    )

    for key in [
        "problem_summary",
        "problem_items",
        "goals",
    ]:
        rule = _require_mapping(
            project_rules,
            key,
            "extraction.project_rules",
        )

        _require_text(
            rule,
            "field",
            f"extraction.project_rules.{key}",
        )

        _require_text(
            rule,
            "text",
            f"extraction.project_rules.{key}",
        )

    user_rules = _require_mapping(
        template,
        "user_rules",
        "extraction",
    )

    _require_text(
        user_rules,
        "field",
        "extraction.user_rules",
    )

    _require_text(
        user_rules,
        "text",
        "extraction.user_rules",
    )

    requirement_rules = _require_mapping(
        template,
        "requirement_rules",
        "extraction",
    )

    for key in [
        "functional",
        "non_functional",
        "data",
        "technical",
    ]:
        rule = _require_mapping(
            requirement_rules,
            key,
            "extraction.requirement_rules",
        )

        _require_text(
            rule,
            "description",
            f"extraction.requirement_rules.{key}",
        )

    decision_rules = _require_mapping(
        template,
        "decision_rules",
        "extraction",
    )

    for key in [
        "feature",
        "non_functional",
        "data",
        "tech",
        "scope",
    ]:
        rule = _require_mapping(
            decision_rules,
            key,
            "extraction.decision_rules",
        )

        _require_text(
            rule,
            "description",
            f"extraction.decision_rules.{key}",
        )

    _require_mapping(
        template,
        "constraint_rules",
        "extraction",
    )


def _validate_fewshots_template(
    template: dict[str, Any],
) -> None:
    metadata = _require_mapping(
        template,
        "metadata",
        "extraction_fewshots",
    )

    _require_text(
        metadata,
        "version",
        "extraction_fewshots.metadata",
    )

    examples = _require_list(
        template,
        "examples",
        "extraction_fewshots",
    )

    if not examples:
        raise PromptTemplateError(
            "extraction_fewshots.examples는 비어 있을 수 없습니다."
        )

    seen_ids: set[str] = set()

    for index, example in enumerate(examples):
        if not isinstance(example, dict):
            raise PromptTemplateError(
                "extraction_fewshots.examples의 각 항목은 객체여야 합니다."
            )

        context = f"extraction_fewshots.examples[{index}]"

        example_id = _require_text(
            example,
            "id",
            context,
        )

        if example_id in seen_ids:
            raise PromptTemplateError(
                f"few-shot id가 중복되었습니다: {example_id}"
            )

        seen_ids.add(example_id)

        _require_text(
            example,
            "input",
            context,
        )

        output = example.get("output")

        if not isinstance(output, dict):
            raise PromptTemplateError(
                f"{context}.output은 객체여야 합니다."
            )

        try:
            MeetingExtraction.model_validate(output)
        except Exception as error:
            raise PromptTemplateError(
                f"{context}.output이 MeetingExtraction 스키마와 맞지 않습니다."
            ) from error


@lru_cache(maxsize=1)
def load_extraction_template() -> dict[str, Any]:
    template = _load_yaml(
        EXTRACTION_TEMPLATE_PATH
    )

    _validate_extraction_template(template)

    return template


@lru_cache(maxsize=1)
def load_extraction_fewshots() -> dict[str, Any]:
    template = _load_yaml(
        EXTRACTION_FEWSHOTS_PATH
    )

    _validate_fewshots_template(template)

    return template


def _append_rules(
    parts: list[str],
    rules: list[Any],
) -> None:
    for index, rule in enumerate(rules, start=1):
        if isinstance(rule, str):
            text = rule.strip()
        elif isinstance(rule, dict):
            text = str(rule.get("text", "")).strip()
        else:
            text = ""

        if text:
            parts.append(f"{index}. {text}")


def build_extraction_system_prompt() -> str:
    """
    extraction.yaml의 규칙을 실제 시스템 프롬프트로 변환합니다.

    YAML에 작성한 세부 rules가 모델 입력에서 누락되지 않도록
    프로젝트, 사용자, 요구사항, 결정사항, 제약사항을 같은 방식으로
    처리합니다.

    이 함수는 문서 내용을 생성하거나 근거를 검증하지 않습니다.
    YAML의 내용을 빠짐없이 전달하는 역할만 합니다.
    """
    template = load_extraction_template()
    parts: list[str] = []

    def append_text(value: Any) -> None:
        """비어 있지 않은 문자열만 추가합니다."""
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())

    def append_rule_list(value: Any) -> None:
        """
        문자열 규칙과 {id, text} 형식의 규칙을 모두 처리합니다.

        규칙에 없는 내용은 추가하지 않습니다.
        """
        if not isinstance(value, list):
            return

        for item in value:
            if isinstance(item, str):
                append_text(item)
            elif isinstance(item, dict):
                append_text(item.get("text"))

    def append_examples(label: str, value: Any) -> None:
        """문자열 또는 객체로 작성된 예시를 표시합니다."""
        if not isinstance(value, list) or not value:
            return

        parts.append(label)

        for item in value:
            if isinstance(item, str):
                append_text(item)

            elif isinstance(item, dict):
                # 제약사항 예시는 type과 content를 가진 객체일 수 있습니다.
                append_text(
                    yaml.safe_dump(
                        item,
                        allow_unicode=True,
                        sort_keys=False,
                    )
                )

    def append_rule_block(
        title: str,
        rule: dict[str, Any],
    ) -> None:
        """
        하나의 규칙 블록을 공통 방식으로 처리합니다.

        기존 코드에서 빠졌던 결정사항 rules와 제약사항 rules도
        이 함수를 통해 실제 프롬프트에 포함됩니다.
        """
        parts.append(title)

        append_text(rule.get("field"))
        append_text(rule.get("description"))
        append_text(rule.get("text"))

        item_fields = rule.get("item_fields")

        if isinstance(item_fields, list):
            names = [
                name.strip()
                for name in item_fields
                if isinstance(name, str) and name.strip()
            ]

            if names:
                parts.append(
                    "항목 필드: " + ", ".join(names)
                )

        append_rule_list(rule.get("rules"))

        append_examples(
            "예시",
            rule.get("examples"),
        )

        append_examples(
            "표현 예시",
            rule.get("expressions"),
        )

    append_text(template["role"])

    parts.append("절대 규칙")
    append_rule_list(template["absolute_rules"])

    parts.append("프로젝트 정보 추출 규칙")

    for key, rule in template["project_rules"].items():
        append_rule_block(
            f"프로젝트 규칙: {key}",
            rule,
        )

    append_rule_block(
        "대상 사용자 추출 규칙",
        template["user_rules"],
    )

    parts.append("요구사항 분류 규칙")

    for key, rule in template["requirement_rules"].items():
        append_rule_block(
            f"requirements.{key}:",
            rule,
        )

    parts.append("결정사항 분류 규칙")

    for key, rule in template["decision_rules"].items():
        append_rule_block(
            f"decisions.category={key}",
            rule,
        )

    constraint_rules = template["constraint_rules"]

    append_rule_block(
        "제약사항 추출 규칙",
        constraint_rules,
    )

    categories = constraint_rules.get("categories")

    if isinstance(categories, list):
        category_names = [
            category.strip()
            for category in categories
            if isinstance(category, str) and category.strip()
        ]

        if category_names:
            parts.append(
                "제약사항 유형: " + ", ".join(category_names)
            )

    # 기존 예시의 내용은 변경하지 않고 그대로 전달합니다.
    for key, title in [
        (
            "mixed_decision_example",
            "확정 내용과 미정 내용 분리 예시",
        ),
        (
            "invalid_output_example",
            "잘못된 출력과 올바른 처리 예시",
        ),
    ]:
        example = template.get(key)

        if isinstance(example, dict) and example:
            parts.append(title)

            append_text(
                yaml.safe_dump(
                    example,
                    allow_unicode=True,
                    sort_keys=False,
                )
            )

    return "\n\n".join(parts)


def build_extraction_fewshot_messages() -> list[dict[str, str]]:
    """few-shot YAML을 채팅 메시지 목록으로 변환합니다."""

    template = load_extraction_fewshots()
    messages: list[dict[str, str]] = []

    for example in template["examples"]:
        validated = MeetingExtraction.model_validate(
            example["output"]
        )

        messages.append(
            {
                "role": "user",
                "content": example["input"].strip(),
            }
        )

        messages.append(
            {
                "role": "assistant",
                "content": json.dumps(
                    validated.model_dump(mode="json"),
                    ensure_ascii=False,
                    indent=2,
                ),
            }
        )

    return messages

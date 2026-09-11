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
    """extraction.yaml을 모델에 전달할 문자열로 변환합니다."""

    template = load_extraction_template()
    parts: list[str] = []

    parts.append(
        _require_text(
            template,
            "role",
            "extraction",
        )
    )

    parts.append("절대 규칙")

    _append_rules(
        parts,
        template["absolute_rules"],
    )

    parts.append("프로젝트 정보 추출 규칙")

    for rule in template["project_rules"].values():
        field = str(rule["field"]).strip()
        text = str(rule["text"]).strip()

        parts.append(field)
        parts.append(text)

    parts.append("요구사항 분류 규칙")

    for key, rule in template["requirement_rules"].items():
        description = str(
            rule["description"]
        ).strip()

        parts.append(f"{key}: {description}")

        rules = rule.get("rules", [])

        if isinstance(rules, list):
            for item in rules:
                if isinstance(item, str) and item.strip():
                    parts.append(item.strip())

        examples = rule.get("examples", [])

        if isinstance(examples, list) and examples:
            example_text = ", ".join(
                str(item).strip()
                for item in examples
                if str(item).strip()
            )

            if example_text:
                parts.append(
                    f"{key} 예시: {example_text}"
                )

    parts.append("결정사항 분류 규칙")

    for key, rule in template["decision_rules"].items():
        description = str(
            rule["description"]
        ).strip()

        parts.append(f"{key}: {description}")

        expressions = rule.get("expressions", [])

        if isinstance(expressions, list) and expressions:
            expression_text = ", ".join(
                str(item).strip()
                for item in expressions
                if str(item).strip()
            )

            if expression_text:
                parts.append(
                    f"{key}에 해당하는 표현: {expression_text}"
                )

    constraint_rules = template["constraint_rules"]

    parts.append("제약사항 추출 규칙")

    categories = constraint_rules.get(
        "categories",
        [],
    )

    if isinstance(categories, list) and categories:
        parts.append(
            "제약사항 유형: "
            + ", ".join(
                str(item).strip()
                for item in categories
                if str(item).strip()
            )
        )

    constraint_text = str(
        constraint_rules.get("text", "")
    ).strip()

    if constraint_text:
        parts.append(constraint_text)

    mixed_example = template.get(
        "mixed_decision_example",
        {},
    )

    if isinstance(mixed_example, dict):
        source = str(
            mixed_example.get("source", "")
        ).strip()

        expected = mixed_example.get(
            "expected",
            {},
        )

        if source and isinstance(expected, dict):
            parts.append("결정 내용과 미정 내용이 섞인 예시")
            parts.append(f"원문:\n{source}")

            decision = str(
                expected.get("decision", "")
            ).strip()

            unresolved = str(
                expected.get("unresolved", "")
            ).strip()

            if decision:
                parts.append(
                    f"decisions에 작성할 내용:\n{decision}"
                )

            if unresolved:
                parts.append(
                    f"unresolved에 작성할 내용:\n{unresolved}"
                )

    invalid_example = template.get(
        "invalid_output_example",
        {},
    )

    if isinstance(invalid_example, dict):
        output = str(
            invalid_example.get("output", "")
        ).strip()

        evidence = str(
            invalid_example.get("evidence", "")
        ).strip()

        problems = invalid_example.get(
            "problems",
            [],
        )

        correct_handling = str(
            invalid_example.get(
                "correct_handling",
                "",
            )
        ).strip()

        if output:
            parts.append("잘못된 출력 예시")
            parts.append(f"잘못된 내용:\n{output}")

        if evidence:
            parts.append(f"잘못된 근거:\n{evidence}")

        if isinstance(problems, list):
            for problem in problems:
                text = str(problem).strip()

                if text:
                    parts.append(text)

        if correct_handling:
            parts.append(
                f"올바른 처리:\n{correct_handling}"
            )

    return "\n\n".join(parts).strip()


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
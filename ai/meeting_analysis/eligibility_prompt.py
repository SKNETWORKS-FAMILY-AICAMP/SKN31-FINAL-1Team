import json
from pathlib import Path

import yaml


PROMPT_PATH = (
    Path(__file__).resolve().parent
    / "prompt_templates"
    / "eligibility.yaml"
)

TEXT_FIELDS = (
    "role",
    "glossary_rules",
    "input_rules",
    "response_rules",
)

RULE_GROUPS = {
    "decision_rules": (
        "relevant",
        "mixed",
        "irrelevant",
        "needs_clarification",
    ),
    "extraction_rules": (
        "scope",
        "source",
        "context",
        "rejection",
    ),
}


def load_template() -> dict:
    """판별 규칙을 읽고 필요한 항목이 있는지 확인한다."""
    with PROMPT_PATH.open(encoding="utf-8") as file:
        template = yaml.safe_load(file)

    if not isinstance(template, dict):
        raise ValueError("판별 프롬프트는 YAML 객체여야 합니다.")

    for key in TEXT_FIELDS:
        value = template.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"판별 프롬프트의 {key} 내용이 필요합니다.")

    for group, keys in RULE_GROUPS.items():
        rules = template.get(group)
        if not isinstance(rules, dict):
            raise ValueError(f"판별 프롬프트의 {group} 설정이 필요합니다.")

        for key in keys:
            value = rules.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{group}.{key} 내용이 필요합니다.")

    examples = template.get("examples")
    if not isinstance(examples, list) or not examples:
        raise ValueError("판별 예시가 하나 이상 필요합니다.")

    for index, example in enumerate(examples, start=1):
        if not isinstance(example, dict):
            raise ValueError(f"판별 예시 {index}의 형식이 잘못되었습니다.")

        text = example.get("input")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"판별 예시 {index}의 입력이 필요합니다.")

        if not isinstance(example.get("output"), dict):
            raise ValueError(f"판별 예시 {index}의 출력이 필요합니다.")

    return template


def build_system_prompt(template: dict) -> str:
    """고정 규칙을 정해진 순서로 조립한다."""
    blocks = [template["role"].strip()]

    for key in RULE_GROUPS["decision_rules"]:
        rule = template["decision_rules"][key].strip()
        blocks.append(f"판정 기준: {key}\n{rule}")

    for key in RULE_GROUPS["extraction_rules"]:
        rule = template["extraction_rules"][key].strip()
        blocks.append(rule)

    for key in ("glossary_rules", "input_rules", "response_rules"):
        blocks.append(template[key].strip())

    return "\n\n".join(blocks)


def build_messages(
    meeting_text: str,
    glossary_text: str = "",
) -> list[dict[str, str]]:
    """고정 규칙, 예시 메시지 쌍, 실제 입력을 조립한다."""
    template = load_template()

    messages = [
        {
            "role": "system",
            "content": build_system_prompt(template),
        }
    ]

    for example in template["examples"]:
        example_input = {
            "meeting_text": example["input"],
            "glossary": "",
        }

        messages.extend([
            {
                "role": "user",
                "content": json.dumps(
                    example_input,
                    ensure_ascii=False,
                ),
            },
            {
                "role": "assistant",
                "content": json.dumps(
                    example["output"],
                    ensure_ascii=False,
                ),
            },
        ])

    actual_input = {
        "meeting_text": meeting_text,
        "glossary": glossary_text,
    }

    messages.append({
        "role": "user",
        "content": json.dumps(
            actual_input,
            ensure_ascii=False,
        ),
    })

    return messages
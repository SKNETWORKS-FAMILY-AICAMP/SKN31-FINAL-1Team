import json
import re
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


# ── mixed 2단계: 문단 번호로 고르게 하는 메시지 ─────────────────
#
# 2026-09-14: mixed 판정에서 개발 관련 구간을 "발췌 전문"으로 받던 것을
# "문단 번호"로 바꿨습니다.
#
# 발췌 전문을 받으면 출력 길이가 회의록 길이에 비례합니다. 실제 회의록
# (전사본 11,000자, 개발 논의 비중 큼)에서 출력 상한 16,384 토큰을 넘겨
# IncompleteOutputException으로 500이 났습니다. 토큰 상한을 올려서는 못
# 고칩니다 — 16,384가 gpt-4o의 최대이고, 회의록이 길어지면 다시 넘습니다.
#
# 번호만 받으면 출력이 숫자 수십 개로 끝나므로 회의록 길이와 무관합니다.
# 덤으로 원문을 코드가 직접 잘라내므로 모델이 글자를 바꿀 수 없습니다.

PARAGRAPH_SYSTEM_PROMPT = """회의록에서 소프트웨어 또는 디지털 서비스 개발 기획과
관련된 문단만 골라내는 작업입니다.

각 문단 앞에 [번호]가 붙어 있습니다. 개발 기획에 활용할 수 있는 문단의
번호만 배열로 반환합니다.

포함할 것:
- 기능, 화면, 데이터, 기술, 개발 범위, 테스트, 배포에 관한 논의
- 프로젝트 배경, 사용자 조사, 현재 업무의 문제, 대상 사용자
- 목표, 정책, 일정, 인력, 결정과 그 이유, 미정 사항
- 위 내용을 판단하는 데 필요한 앞뒤 문맥

제외할 것:
- 일상 대화, 잡담, 개인 신상, 여행이나 식사 이야기
- 인사말과 회의 진행에 관한 말만 있는 문단

애매하면 포함합니다. 뺀 문단은 다음 단계에서 볼 수 없습니다.
문단 내용을 다시 쓰지 말고 번호만 반환합니다."""


# 단독으로는 뜻이 없는 짧은 줄의 기준.
#
# 2026-09-14: 실제 회의 전사본에서 줄 단위로만 쪼갰더니 "네.", "맞아요.",
# "생각보다 분류를 잘하네요." 같은 맞장구가 각각 별도 문단이 됐습니다.
# 200개 가까운 조각이 생겼고, 모델이 그중 의미 있어 보이는 것만 고르면서
# 앞뒤 맥락이 끊겼습니다. 기술 스택 논의가 통째로 빠졌습니다.
#
# 맞장구는 앞 발언에 속합니다. 앞 문단에 붙이면 각 문단이 온전한 대화
# 단위가 되고 문단 수도 크게 줄어듭니다.
SHORT_LINE_CHARS = 30


def number_paragraphs(meeting_text: str) -> list[tuple[int, str]]:
    """회의록을 문단으로 쪼개 1부터 번호를 붙인다.

    빈 줄과 줄바꿈을 경계로 나누되, 짧은 줄은 앞 문단에 붙입니다.
    대화 전사본에서 맥락이 끊기는 것을 막습니다.
    """
    lines = [
        line.strip()
        for line in re.split(r"\n\s*\n|\n", meeting_text)
    ]

    merged: list[str] = []

    for line in lines:
        if not line:
            continue

        # 짧은 줄은 앞 문단에 붙입니다.
        # 첫 줄이 짧으면 붙일 앞 문단이 없으므로 그대로 둡니다.
        if merged and len(line) < SHORT_LINE_CHARS:
            merged[-1] = f"{merged[-1]}\n{line}"
            continue

        merged.append(line)

    return list(enumerate(merged, start=1))


def build_paragraph_messages(
    numbered: list[tuple[int, str]],
) -> list[dict[str, str]]:
    """번호를 붙인 회의록으로 2단계 메시지를 만든다."""
    body = "\n".join(
        f"[{number}] {text}"
        for number, text in numbered
    )

    return [
        {
            "role": "system",
            "content": PARAGRAPH_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": body,
        },
    ]
"""a2_1_requirement_draft/prompt_builder.py"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml

from .schemas import PlanDocument

PROMPT_DIR = Path(__file__).parent / "prompts"


@lru_cache(maxsize=1)
def load_template() -> Dict[str, Any]:
    with open(PROMPT_DIR / "requirements_template.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_nfr_checklist() -> Dict[str, Any]:
    with open(PROMPT_DIR / "nfr_checklist.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _render_few_shots(examples: list) -> str:
    blocks = []
    for i, ex in enumerate(examples, start=1):
        blocks.append(
            f"[예시 {i}] {ex.get('description', '')}\n"
            f"입력:\n{json.dumps(ex['input'], ensure_ascii=False, indent=2)}\n"
            f"출력:\n{json.dumps(ex['output'], ensure_ascii=False, indent=2)}"
        )
    return "\n\n".join(blocks)


def _render_nfr_checklist(checklist: Dict[str, Any]) -> str:
    lines = []
    all_categories = checklist.get("standard_categories", []) + checklist.get(
        "project_specific_categories", []
    )
    for cat in all_categories:
        mode_label = "[항상 생성]" if cat["generation_mode"] == "baseline" else "[조건부 생성]"
        example = cat.get("example", {})
        lines.append(
            f"- {cat['name_kr']} ({cat['id']}) {mode_label}\n"
            f"  하위특성: {', '.join(cat.get('sub_characteristics', []))}\n"
            f"  적용 조건: {cat.get('trigger_hint', '-')}\n"
            f"  예시 형식: {example.get('name', '')} — {example.get('description', '')}"
        )
    return "\n".join(lines)


def build_system_prompt(plan: PlanDocument) -> str:
    template = load_template()
    checklist = load_nfr_checklist()

    return f"""{template['role']}

{template['constraints']}

[표준 비기능요구사항 체크리스트]
{_render_nfr_checklist(checklist)}

[출력 예시]
{_render_few_shots(template['few_shot_examples'])}

---
아래는 이번에 처리할 실제 기획서다. 위 규칙과 예시를 따라 요구사항정의서를 생성하라.

[기획서]
{json.dumps(plan.model_dump(exclude_none=True), ensure_ascii=False, indent=2)}
"""


def build_messages(plan: PlanDocument) -> list:
    return [
        {"role": "system", "content": build_system_prompt(plan)},
        {"role": "user", "content": "위 기획서를 바탕으로 요구사항정의서 초안을 생성하라."},
    ]

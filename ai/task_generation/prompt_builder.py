"""a2_2_task_generation/prompt_builder.py"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml

PROMPT_DIR = Path(__file__).parent / "prompts"


@lru_cache(maxsize=1)
def load_template() -> dict:
    with open(PROMPT_DIR / "template.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_task_type() -> dict:
    with open(PROMPT_DIR / "task_type.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _render_few_shots(examples: list) -> str:
    blocks = []
    for i, ex in enumerate(examples, start=1):
        blocks.append(
            f"[예시 {i}]\n입력:\n{json.dumps(ex['input'], ensure_ascii=False, indent=2)}\n"
            f"출력:\n{json.dumps(ex['output'], ensure_ascii=False, indent=2)}"
        )
    return "\n\n".join(blocks)


def build_system_prompt(requirement_doc: Dict[str, Any], participant_count: int) -> str:
    t = load_template()
    tt = load_task_type()

    constraints = t["constraints"].format(min_tasks=participant_count)
    type_list = "\n".join(f"- {x['name_kr']} ({x['id']})" for x in tt["task_types"])

    return f"""{t['role']}

{constraints}

[업무유형 목록]
{type_list}

[업무 분해 원칙]
{tt['decomposition_principles']}
Depth: {tt['depth']}

[계층/ID 규칙]
{tt['hierarchy_rules']}

[출력 예시]
{_render_few_shots(t['few_shot_examples'])}

---
아래는 이번에 처리할 실제 요구사항정의서다. (참여인원: {participant_count}명)

[요구사항정의서]
{json.dumps(requirement_doc, ensure_ascii=False, indent=2)}
"""

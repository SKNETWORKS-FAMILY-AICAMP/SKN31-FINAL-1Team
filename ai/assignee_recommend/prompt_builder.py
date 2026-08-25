"""a2_3_assignee_recommend/prompt_builder.py"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import yaml

PROMPT_DIR = Path(__file__).parent / "prompts"


@lru_cache(maxsize=1)
def load_template() -> dict:
    with open(PROMPT_DIR / "template.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _render_few_shots(examples: list) -> str:
    blocks = []
    for i, ex in enumerate(examples, start=1):
        blocks.append(
            f"[예시 {i}]\n입력:\n{json.dumps(ex['input'], ensure_ascii=False, indent=2)}\n"
            f"출력:\n{json.dumps(ex['output'], ensure_ascii=False, indent=2)}"
        )
    return "\n\n".join(blocks)


def build_system_prompt(task_id: str, candidates: List[Dict[str, Any]]) -> str:
    t = load_template()
    return f"""{t['role']}

{t['constraints']}

[출력 예시]
{_render_few_shots(t['few_shot_examples'])}

---
아래는 이번 업무와, 코드가 이미 1차 필터링·순위화한 후보 목록이다.
순위(rule_score)는 바꾸지 말고, 각 후보의 근거 문장만 작성하라.

[업무 ID]
{task_id}

[후보 목록]
{json.dumps(candidates, ensure_ascii=False, indent=2)}
"""

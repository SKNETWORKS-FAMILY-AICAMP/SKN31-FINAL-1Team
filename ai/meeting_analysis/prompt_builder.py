"""a1_1_meeting_analysis/prompt_builder.py"""

import json
from functools import lru_cache
from pathlib import Path

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
            f"[예시 {i}]\n입력:\n{ex['input']}\n"
            f"출력:\n{json.dumps(ex['output'], ensure_ascii=False, indent=2)}"
        )
    return "\n\n".join(blocks)


def build_system_prompt(meeting_text: str) -> str:
    t = load_template()
    return f"""{t['role']}

{t['constraints']}

[출력 예시]
{_render_few_shots(t['few_shot_examples'])}

---
아래는 이번에 분석할 실제 회의록이다.

[회의록]
{meeting_text}
"""

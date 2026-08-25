"""a1_2_plan_draft/prompt_builder.py"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

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


def build_system_prompt(
    structured_analysis: Dict[str, Any], rejection_reason: Optional[str] = None
) -> str:
    t = load_template()
    rejection_block = (
        f"\n[이전 반려 사유 — 반드시 반영할 것]\n{rejection_reason}\n" if rejection_reason else ""
    )
    return f"""{t['role']}

{t['constraints']}

[출력 예시]
{_render_few_shots(t['few_shot_examples'])}
{rejection_block}
---
아래는 이번에 처리할 실제 구조화 분석 결과다.

[구조화 분석 결과]
{json.dumps(structured_analysis, ensure_ascii=False, indent=2)}
"""

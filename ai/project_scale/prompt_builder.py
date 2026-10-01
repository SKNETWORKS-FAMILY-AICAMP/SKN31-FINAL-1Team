"""project_scale/prompt_builder.py"""

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


def _render_few_shots(examples: list) -> str:
    blocks = []
    for i, ex in enumerate(examples, start=1):
        blocks.append(
            f"[예시 {i}] {ex.get('description', '')}\n"
            f"입력:\n{json.dumps(ex['input'], ensure_ascii=False, indent=2)}\n"
            f"출력:\n{json.dumps(ex['output'], ensure_ascii=False, indent=2)}"
        )
    return "\n\n".join(blocks)


def build_complexity_prompt(project_context: Dict[str, Any]) -> str:
    """
    기획서(SpecDocument) 상위 맥락 5개 필드(overview/problem_definition/
    key_features/tech_stack/final_decisions)를 그대로 넘긴다. backend가
    조립해서 넘기는 dict를 그대로 받는다 — 이 모듈은 DB를 모른다.
    """
    t = load_template()
    return f"""{t['role']}

{t['constraints']}

[판단 예시]
{_render_few_shots(t['few_shot_examples'])}

---
아래는 이번에 판단할 실제 기획서 요약 정보다.

[기획서 요약]
{json.dumps(project_context, ensure_ascii=False, indent=2)}
"""

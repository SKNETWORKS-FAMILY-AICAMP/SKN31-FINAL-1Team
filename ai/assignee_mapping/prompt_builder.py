"""assignee_mapping/prompt_builder.py"""

import json
from functools import lru_cache
from pathlib import Path

import yaml

from .schemas import RawEmployeeProfile

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


def build_extraction_prompt(profile: RawEmployeeProfile) -> str:
    """
    career_history_text 하나만 LLM에게 넘긴다. skills/certifications는 이미
    구조화된 DB 값이라 LLM이 볼 필요가 없다 — 그대로 코드가 복사해서 쓴다
    (agent.py의 EmployeeFitnessProfile 조립 부분 참고).
    """
    t = load_template()
    return f"""{t['role']}

{t['constraints']}

[추출 예시]
{_render_few_shots(t['few_shot_examples'])}

---
아래는 이번에 처리할 실제 경력기술서 원문이다.

[경력기술서]
{json.dumps({"career_history_text": profile.career_history_text}, ensure_ascii=False, indent=2)}
"""

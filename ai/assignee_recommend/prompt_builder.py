"""a2_3_assignee_recommend/prompt_builder.py"""

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


def build_reason_prompt(unit: Dict[str, Any], candidate: Dict[str, Any]) -> str:
    """코드가 이미 확정한 담당자에 대한 근거 문장(skill_fit/workload/similar_experience)을 시킨다."""
    t = load_template()
    return f"""{t['role']}

{t['reason_constraints']}

[근거 작성 예시]
{_render_few_shots(t['reason_few_shot_examples'])}

---
아래는 이번 업무와, 코드가 이미 확정한 담당자다. score는 절대 바꾸지 말고,
skill_fit/workload/similar_experience 세 문장만 작성하라.

[업무]
{json.dumps(
    {
        "unit_id": unit["unit_id"],
        "title": unit["title"],
        "description": unit["description"],
        "required_skills": unit.get("required_skills", []),
    },
    ensure_ascii=False,
    indent=2,
)}

[확정된 담당자]
{json.dumps(
    {
        "employee_id": candidate["employee_id"],
        "skill_match": candidate["skill_match"],
        "workload": candidate["workload"],
        "similar_experience": candidate["similar_experience"],
        "score": candidate["score"],
    },
    ensure_ascii=False,
    indent=2,
)}
"""


def build_hold_prompt(unit: Dict[str, Any]) -> str:
    """조건을 만족하는 담당자가 없어 보류된 업무에 대한 보류 사유 설명을 시킨다."""
    t = load_template()
    return f"""{t['role']}

{t['hold_constraints']}

[보류 설명 예시]
{_render_few_shots(t['hold_few_shot_examples'])}

---
아래 업무는 코드가 조건(요구 기술 매칭 + 가용시간)을 만족하는 담당자를 찾지
못해 배정을 보류했다. 왜 보류됐는지 한 문장으로 설명하라.

[업무]
{json.dumps(
    {
        "unit_id": unit["unit_id"],
        "title": unit["title"],
        "required_skills": unit.get("required_skills", []),
    },
    ensure_ascii=False,
    indent=2,
)}
"""

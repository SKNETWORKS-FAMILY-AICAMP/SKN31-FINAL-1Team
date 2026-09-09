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


def build_reason_batch_prompt(items: List[Dict[str, Any]]) -> str:
    """
    여러 업무의 근거 문장을 한 번의 LLM 호출로 생성한다(OpenAI TPM 한도 때문에
    유닛 1개당 1회 호출하던 것을 묶음 — agent.py의 generate_reasons_batch 참고).
    각 item은 {"unit": <스케줄러가 만든 unit dict>, "employee_id": ..., "score": ...,
    "skill_match": ..., "workload": ..., "similar_experience": ...} 형태
    (rule_filter.schedule_assignments()의 반환 항목 그대로).
    """
    t = load_template()
    payload = [
        {
            "unit_id": item["unit"]["unit_id"],
            "title": item["unit"]["title"],
            "description": item["unit"]["description"],
            "required_skills": item["unit"].get("required_skills", []),
            "employee_id": item["employee_id"],
            "skill_match": item["skill_match"],
            "workload": item["workload"],
            "similar_experience": item["similar_experience"],
            "score": item["score"],
        }
        for item in items
    ]
    return f"""{t['role']}

{t['reason_constraints']}

[근거 작성 예시]
{_render_few_shots(t['reason_few_shot_examples'])}

---
아래는 이번에 한 번에 처리할 여러 업무와, 코드가 이미 확정한 담당자들이다. score는
절대 바꾸지 말고, 각 업무마다 skill_fit/workload/similar_experience 세 문장을
작성하라. 결과는 unit_id로 원본과 매칭해야 한다 — 입력받은 unit_id 전부에 대해
빠짐없이 반환하라.

[업무 · 확정된 담당자 목록]
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def build_hold_batch_prompt(units: List[Dict[str, Any]]) -> str:
    """
    여러 업무의 보류 사유를 한 번의 LLM 호출로 생성한다
    (agent.py의 generate_hold_explanations_batch 참고).
    """
    t = load_template()
    payload = [
        {
            "unit_id": u["unit_id"],
            "title": u["title"],
            "required_skills": u.get("required_skills", []),
        }
        for u in units
    ]
    return f"""{t['role']}

{t['hold_constraints']}

[보류 설명 예시]
{_render_few_shots(t['hold_few_shot_examples'])}

---
아래 업무들은 코드가 조건(요구 기술 매칭 + 가용시간)을 만족하는 담당자를 각각
찾지 못해 배정을 보류했다. 각 업무마다 왜 보류됐는지 한 문장으로 설명하라.
결과는 unit_id로 원본과 매칭해야 한다 — 입력받은 unit_id 전부에 대해 빠짐없이
반환하라.

[보류된 업무 목록]
{json.dumps(payload, ensure_ascii=False, indent=2)}
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

"""a2_3_assignee_recommend/prompt_builder.py"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Tuple

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


# --- 배치 프롬프트 (2026-09, OpenAI TPM 레이트리밋 대응) ---
#
# unit마다 별도 호출하면 unit 수만큼 LLM 호출이 늘어난다. 아래 두 함수는
# 여러 unit을 하나의 프롬프트 안에 번호를 매겨 나열하고, 응답도 unit_id로
# 태깅된 결과 배열 하나로 한 번에 받는다. 각 unit에 대해 요구하는 내용
# (제약조건·근거 3종/보류 사유 한 문장)은 단건 프롬프트와 동일하다 — 다만
# "여러 건을 한 번에" 처리하라는 지시와 unit_id 매칭 규칙만 덧붙인다.


def build_batch_reason_prompt(units_and_candidates: List[Tuple[Dict[str, Any], Dict[str, Any]]]) -> str:
    """여러 (unit, 확정된 담당자) 쌍에 대한 근거 문장을 한 번의 응답으로 받기 위한 프롬프트."""
    t = load_template()
    items = []
    for unit, candidate in units_and_candidates:
        items.append(
            {
                "unit": {
                    "unit_id": unit["unit_id"],
                    "title": unit["title"],
                    "description": unit["description"],
                    "required_skills": unit.get("required_skills", []),
                },
                "candidate": {
                    "employee_id": candidate["employee_id"],
                    "skill_match": candidate["skill_match"],
                    "workload": candidate["workload"],
                    "similar_experience": candidate["similar_experience"],
                    "score": candidate["score"],
                },
            }
        )
    return f"""{t['role']}

{t['reason_constraints']}

[근거 작성 예시]
{_render_few_shots(t['reason_few_shot_examples'])}

---
아래는 이번에 처리할 업무 {len(items)}건이다. 각 항목은 이미 코드가 확정한
담당자를 포함하고 있다. score는 절대 바꾸지 말고, 각 항목마다
skill_fit/workload/similar_experience 세 문장을 작성하라.

반드시 지켜야 할 것:
- results 배열의 원소 수는 아래 [업무 목록]의 항목 수와 정확히 같아야 한다.
- 각 결과의 unit_id는 [업무 목록]에 있는 해당 항목의 unit_id와 정확히
  일치해야 한다(누락·중복·변형 금지).
- 항목끼리 내용을 섞지 마라 — 각 unit_id의 근거는 오직 그 항목의 [업무]와
  [확정된 담당자] 정보만 사용해 작성한다.

[업무 목록] (총 {len(items)}건)
{json.dumps(items, ensure_ascii=False, indent=2)}
"""


def build_batch_hold_prompt(units: List[Dict[str, Any]]) -> str:
    """여러 unit에 대한 보류 사유 설명을 한 번의 응답으로 받기 위한 프롬프트."""
    t = load_template()
    items = [
        {
            "unit_id": unit["unit_id"],
            "title": unit["title"],
            "required_skills": unit.get("required_skills", []),
        }
        for unit in units
    ]
    return f"""{t['role']}

{t['hold_constraints']}

[보류 설명 예시]
{_render_few_shots(t['hold_few_shot_examples'])}

---
아래 업무 {len(items)}건은 모두 코드가 조건(요구 기술 매칭 + 가용시간)을
만족하는 담당자를 찾지 못해 배정을 보류했다. 각 업무마다 왜 보류됐는지
한 문장으로 설명하라.

반드시 지켜야 할 것:
- results 배열의 원소 수는 아래 [업무 목록]의 항목 수와 정확히 같아야 한다.
- 각 결과의 unit_id는 [업무 목록]에 있는 해당 항목의 unit_id와 정확히
  일치해야 한다(누락·중복·변형 금지).
- 항목끼리 내용을 섞지 마라 — 각 unit_id의 설명은 오직 그 항목의
  required_skills만 근거로 삼는다.

[업무 목록] (총 {len(items)}건)
{json.dumps(items, ensure_ascii=False, indent=2)}
"""

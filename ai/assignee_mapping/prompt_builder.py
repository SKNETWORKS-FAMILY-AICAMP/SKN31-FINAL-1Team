"""assignee_mapping/prompt_builder.py"""

import json
from functools import lru_cache
from pathlib import Path
from typing import List

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


def build_extraction_batch_prompt(profiles: List[RawEmployeeProfile]) -> str:
    """
    여러 명의 경력기술서를 한 번의 LLM 호출로 처리한다(OpenAI TPM 한도 때문에
    직원 1인당 1회 호출하던 것을 묶음 — agent.py의 extract_experience_tags_batch 참고).
    기존 [추출 예시] few-shot을 그대로 재사용한다 — 단건 예시가 태그 추출 품질/톤
    기준을 이미 보여주므로, 배치 여부와 무관하게 같은 기준을 적용하면 된다.
    """
    t = load_template()
    items = [
        {"employee_id": p.employee_id, "career_history_text": p.career_history_text}
        for p in profiles
    ]
    return f"""{t['role']}

{t['constraints']}

[추출 예시]
{_render_few_shots(t['few_shot_examples'])}

---
아래는 이번에 한 번에 처리할 여러 명의 경력기술서 원문이다. 각 결과는 employee_id로
원본과 매칭해야 한다 — 입력받은 employee_id 전부에 대해 빠짐없이 결과를 반환하라.
경력기술서가 비어 있어도 해당 employee_id는 빈 tags로 포함시켜라.

[경력기술서 목록]
{json.dumps(items, ensure_ascii=False, indent=2)}
"""

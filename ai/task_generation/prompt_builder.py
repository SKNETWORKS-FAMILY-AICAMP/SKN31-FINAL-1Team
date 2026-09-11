"""a2_2_task_generation/prompt_builder.py"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

PROMPT_DIR = Path(__file__).parent / "prompts"


@lru_cache(maxsize=1)
def load_template() -> dict:
    with open(PROMPT_DIR / "template.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_decomposition_rules() -> dict:
    with open(PROMPT_DIR / "decomposition_rules.yaml", encoding="utf-8") as f:
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
    requirement_doc: Dict[str, Any],
    available_skills: Optional[List[str]] = None,
    project_period: Optional[Dict[str, Any]] = None,
) -> str:
    t = load_template()
    tt = load_decomposition_rules()

    # available_skills가 주어지면(호출부가 DB SKILL_* CommonCode 명단을 넘겨준
    # 경우) required_skills를 그 명단 안에서만 고르도록 제약한다 — 이렇게 해야
    # A2-3(assignee_recommend)의 스킬 매칭이 표기 불일치로 실패하는 걸 사후
    # 정규화가 아니라 애초에 어휘를 하나로 맞춰서 막을 수 있다(agent.py의
    # verify_skill_vocabulary/_remap_skill_vocabulary 참고). 안 주어지면(예:
    # 아직 backend 연동 전인 manual_run 스크립트) 기존처럼 자유 텍스트로 둔다.
    skill_constraint = ""
    if available_skills:
        skill_constraint = f"""

[스킬 어휘 제약]
required_skills는 반드시 아래 허용된 스킬 명단 안에서만 골라 써라. 명단에 없는
표현(동의어·다른 표기 포함)을 새로 지어내지 마라. 이 업무에 정말 필요한 기술인데
명단에 대응되는 값이 없으면, 가장 가까운 명단 값을 쓰거나 비워둬라.

[허용된 스킬 명단]
{json.dumps(available_skills, ensure_ascii=False)}"""

    # 2026-09-11: 프로젝트 기간을 estimated_hours 산정의 참고 신호로 준다(팀 결정).
    # project_period가 없으면(예: manual_run, graph.py 경로) 기존처럼 기간을 전혀
    # 모르는 채로 난이도만 보고 산정한다.
    period_context = ""
    if project_period:
        period_context = f"""

[프로젝트 기간 — 참고용]
시작일 {project_period.get('start_date')} ~ 종료일 {project_period.get('end_date')}
(평일 {project_period.get('workdays')}일)

이 프로젝트가 이 기간으로 계획됐다는 건, 전체 업무가 이 안에서 여유 있게 끝날
수 있는 규모라는 뜻이다. estimated_hours를 정할 때 난이도와 함께 이 기간을
참고하라:
  - 기간이 넉넉하면(요구사항 수 대비 평일 수가 많으면) 중/상 난이도 업무에
    검토·재작업 여유를 더 넉넉히 반영하라.
  - 기간이 빠듯하면 여유를 최소화하되, 실제 작업 범위 자체를 줄이지는 마라.
  - 같은 난이도라도 업무 성격에 따라 필요한 시간은 다르다 — 기간에 맞추려고
    업무들을 억지로 균등하게 나누지 말고, difficulty_reason에 쓴 근거에
    비례해서 배분하라."""

    return f"""{t['role']}

{t['constraints']}{skill_constraint}{period_context}

[업무 분해 원칙]
{tt['decomposition_principles']}
Depth: {tt['depth']}

[계층/ID 규칙]
{tt['hierarchy_rules']}

[출력 예시]
{_render_few_shots(t['few_shot_examples'])}

---
아래는 이번에 처리할 실제 요구사항정의서다.

[요구사항정의서]
{json.dumps(requirement_doc, ensure_ascii=False, indent=2)}
"""


def build_skill_remap_prompt(violating_tasks: List[Dict[str, Any]], available_skills: List[str]) -> str:
    """
    verify_skill_vocabulary()가 찾아낸, 허용 명단 밖 스킬을 쓴 업무들만 좁혀서
    다시 고르게 하는 재시도 프롬프트(agent.py의 _remap_skill_vocabulary 참고).
    어떤 값으로 대체할지 판단하려면 업무 맥락(제목/설명)이 필요해, 위반한
    task_id·스킬뿐 아니라 title/description도 함께 보낸다.

    violating_tasks: [{"task_id", "title", "description", "required_skills"}, ...]
    """
    t = load_template()
    return f"""{t['role']}

아래 업무들의 required_skills 중 일부가 허용된 스킬 명단에 없다. 각 업무의
제목/설명을 참고해서, 명단 안에서 가장 가까운 값으로 required_skills 전체를
다시 채워라. 정말 대응되는 값이 없으면 원래 값을 그대로 둬도 된다. 결과는
task_id로 원본과 매칭해야 한다 — 입력받은 task_id 전부에 대해 빠짐없이 반환하라.

[허용된 스킬 명단]
{json.dumps(available_skills, ensure_ascii=False)}

[명단 밖 스킬을 쓴 업무 목록]
{json.dumps(violating_tasks, ensure_ascii=False, indent=2)}
"""

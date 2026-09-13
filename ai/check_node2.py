"""
노드2 LLM이 세부 목표(goals)를 실제로 무엇을 내는지 확인합니다.

3번 섹션이 비는 원인이 두 가지 중 무엇인지 가릅니다.
  A) LLM이 goals를 빈 배열로 낸다        → 프롬프트 문제
  B) LLM은 냈는데 근거 대조에서 탈락한다  → 조립 코드 문제

사용법:
    cd ~/projects/SKN31-FINAL-1Team/ai
    python3 check_node2.py
"""
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

from plan_draft.agent import _call
from plan_draft.prompts import build_messages, build_system_prompt
from plan_draft.schemas import PlanSections
from plan_draft import list_builder

structured = json.loads(
    Path("out/meeting_note_1_complete.json").read_text(encoding="utf-8")
)

result: PlanSections = _call(
    build_system_prompt(""),
    build_messages(structured, ""),
    PlanSections,
    context="진단",
)

print("=" * 64)
print(f"LLM이 낸 goals: {len(result.goals)}건")
print("=" * 64)

for index, goal in enumerate(result.goals):
    print(f"\n[{index}] title : {goal.title}")
    print(f"    problem: {goal.problem}")
    print(f"    goal   : {goal.goal}")
    for evidence in goal.problem_evidence:
        print(f"    p.quote: {evidence.quote[:70]}")
    for evidence in goal.goal_evidence:
        print(f"    g.quote: {evidence.quote[:70]}")

section = list_builder.build_goals(structured, result.goals)

print("\n" + "=" * 64)
print(f"조립 후 채택된 항목: {len(section.items)}건")
print("=" * 64)
for item in section.items:
    print(" -", item.replace("\n", " / "))

print("\n>>> 진단")
if not result.goals:
    print("    A) LLM이 goals를 아예 안 냈습니다 → 프롬프트를 고쳐야 합니다.")
elif not section.items:
    print("    B) LLM은 냈는데 근거 대조에서 전부 탈락했습니다 → 조립 코드 문제입니다.")
    print("       위 p.quote / g.quote를 노드1의 quote와 비교해 보세요.")
else:
    print("    정상 동작합니다.")
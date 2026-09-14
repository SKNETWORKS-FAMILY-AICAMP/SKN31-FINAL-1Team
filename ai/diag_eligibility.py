"""
meeting_note_3_long 실패 원인 진단.

assess_meeting()은 판정과 검증을 한 번에 하고 예외를 던지므로,
LLM 판정만 따로 부른 뒤 발췌문을 하나씩 대조한다.

사용법:
    cd ~/projects/SKN31-FINAL-1Team/ai
    python3 diag_eligibility.py
    python3 diag_eligibility.py meeting_note_1_complete   # 다른 회의록
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

from meeting_analysis.eligibility import MeetingEligibility, find_original_passage
from meeting_analysis.eligibility_prompt import build_messages
from shared.llm_client import get_client
from shared.retry_config import MODEL, TEMPERATURE, MAX_RETRIES

stem = sys.argv[1] if len(sys.argv) > 1 else "meeting_note_3_long"
text = Path(f"tests/fixtures/{stem}.md").read_text(encoding="utf-8")

result = get_client(MODEL).chat.completions.create(
    model=MODEL,
    response_model=MeetingEligibility,
    max_retries=MAX_RETRIES,
    temperature=TEMPERATURE,
    messages=build_messages(meeting_text=text, glossary_text=""),
)

print(f"회의록 : {stem} ({len(text)}자)")
print(f"판정   : {result.status}")
print(f"발췌   : {len(result.relevant_passages)}건")
print("─" * 74)

cursor = 0
counts = {"OK": 0, "순서문제": 0, "원문없음": 0}

for i, passage in enumerate(result.relevant_passages):
    전체 = find_original_passage(passage, text, 0)
    커서 = find_original_passage(passage, text, cursor)

    if 커서:
        verdict = "OK"
        cursor += 커서.end()
    elif 전체:
        verdict = "순서문제"
    else:
        verdict = "원문없음"

    counts[verdict] += 1
    print(f"[{i:>2}] {verdict:<9} {passage[:48]}")

print("─" * 74)
print(f"정상 {counts['OK']} / 순서문제 {counts['순서문제']} / 원문없음 {counts['원문없음']}")
print()

if counts["순서문제"]:
    print("→ 원인: 커서 전진 방식. 발췌문이 원문 순서와 달라 뒤에서 못 찾음.")
    print("  전체 원문에는 존재하므로 지어낸 것이 아님.")
if counts["원문없음"]:
    print("→ 원인: 발췌문이 원문과 불일치. 문장부호 변형 가능성.")
    print("  find_original_passage는 공백만 허용하고 문장부호는 정확히 일치를 요구함.")
if not counts["순서문제"] and not counts["원문없음"]:
    print("→ 이번 실행은 전부 통과. 실패가 실행마다 재현되지 않는 유형.")
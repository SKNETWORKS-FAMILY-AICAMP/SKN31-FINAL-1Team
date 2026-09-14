"""
근거 검증 실패 항목 진단 — LLM을 호출하지 않습니다.

eval_a1.py가 남긴 out/<회의록>.json을 읽어서
unverified 항목의 인용문이 원문의 어느 지점에서 어긋났는지 보여줍니다.
rationale이 원문에 근거한 것인지도 함께 확인합니다.

사용법:
    cd ~/projects/SKN31-FINAL-1Team/ai
    python3 diag_quotes.py                      # meeting_note_3_long
    python3 diag_quotes.py meeting_note_1_complete
"""
import json
import sys
from pathlib import Path

from meeting_analysis.validators.evidence import normalize

STEM = sys.argv[1] if len(sys.argv) > 1 else "meeting_note_3_long"

out_path = Path("out") / f"{STEM}.json"
src_path = Path("tests/fixtures") / f"{STEM}.md"
if not out_path.exists():
    sys.exit(f"{out_path} 가 없습니다. 먼저 eval_a1.py를 돌리세요.")

data = json.loads(out_path.read_text(encoding="utf-8"))
raw_src = src_path.read_text(encoding="utf-8")
src = normalize(raw_src)


def longest_prefix(q: str) -> int:
    """정규화한 인용문이 원문과 몇 글자까지 이어지는지."""
    best = 0
    for i in range(1, len(q) + 1):
        if q[:i] in src:
            best = i
        else:
            break
    return best


def walk(node, path=""):
    if isinstance(node, dict):
        if node.get("evidence_status") == "unverified":
            yield path, node
        for k, v in node.items():
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}[{i}]")


print(f"회의록: {STEM}\n")
print("── 근거 대조 실패 항목 ──")
found = 0
for path, node in walk(data):
    found += 1
    content = str(node.get("content") or node.get("name") or "")
    ev = node.get("evidence") or {}
    quote = str(ev.get("quote") or "")
    nq = normalize(quote)
    cut = longest_prefix(nq)
    print(f"\n[{path}]")
    print(f"  내용      : {content[:90]}")
    print(f"  인용      : {quote[:90]}")
    print(f"  내용 원문존재: {'예' if normalize(content) in src else '아니오'}")
    print(f"  일치한 부분 : {nq[:cut][:70]}")
    print(f"  끊긴 지점  : {nq[cut:cut+24] or '(없음 — 전체 일치)'}")

if not found:
    print("  없음 — 전부 통과")

print("\n\n── 결정 사유 점검 ──")
print("  rationale은 quote와 달리 원문 그대로일 필요가 없습니다.")
print("  아래 '원문과 불일치'는 결함이 아니라 눈으로 확인할 목록입니다.")
for i, d in enumerate(data.get("decisions") or []):
    r = str(d.get("rationale") or "").strip()
    if not r:
        print(f"\n[decisions[{i}]] 사유 없음")
        print(f"  내용: {str(d.get('content'))[:80]}")
    else:
        grounded = normalize(r) in src
        mark = "원문 그대로" if grounded else "원문과 불일치 — 확인 필요"
        print(f"\n[decisions[{i}]] {mark}")
        print(f"  내용: {str(d.get('content'))[:80]}")
        print(f"  사유: {r[:80]}")
"""
회수율 개선이 먹혔는지 확인합니다.

사용법:
    cd ~/projects/SKN31-FINAL-1Team/ai
    python3 -m meeting_analysis.node tests/fixtures/meeting_note_1_complete.md
    python3 check_recall.py
"""
import json
from pathlib import Path

data = json.loads(
    Path("out/meeting_note_1_complete.json").read_text(encoding="utf-8")
)
reqs = data.get("requirements") or {}

print("=" * 66)
print("③ 6번 기술 스택 — requirements.technical")
print("=" * 66)
technical = reqs.get("technical") or []
for item in technical:
    print(f"  - {item.get('content')}")

targets = {
    "BarcodeDetector 또는 웹 카메라": ["barcodedetector", "카메라"],
    "ZXing 폴백": ["zxing"],
    "POS A사 API": ["pos"],
    "Next.js 미채택": ["next.js"],
}
joined = " ".join(str(i.get("content", "")) for i in technical).lower()
print()
for label, keys in targets.items():
    hit = any(k in joined for k in keys)
    print(f"  [{'O' if hit else ' '}] {label}")

print("\n" + "=" * 66)
print("④ 7번 결정 분류 — 구현 방식이 tech로 갔는가")
print("=" * 66)
for decision in data.get("decisions") or []:
    content = str(decision.get("content", ""))
    category = decision.get("category")
    mark = ""
    if "barcodedetector" in content.lower() or "웹 카메라" in content:
        mark = "  <-- tech 여야 함" if category != "tech" else "  <-- OK"
    print(f"  [{category}] {content[:52]}{mark}")

print("\n" + "=" * 66)
print("② 5번 기능 개수 — feature_name 분포")
print("=" * 66)
names: dict[str, int] = {}
for item in reqs.get("functional") or []:
    names[item.get("feature_name") or "(null)"] = (
        names.get(item.get("feature_name") or "(null)", 0) + 1
    )
for name, count in names.items():
    print(f"  {name} ({count}건)")
print(f"\n  상위 기능 {len(names)}개 "
      f"(기대: MVP 6개 + POS 연동 1 = 7개)")
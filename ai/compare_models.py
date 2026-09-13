"""
같은 회의록을 여러 설정으로 돌린 결과를 나란히 비교합니다.

회수율만 보면 속습니다. 회수율이 오르면서 창작도 같이 늘 수 있으므로
근거 검증률과 분류 정확도를 함께 봅니다.

사용법:
    cd ~/projects/SKN31-FINAL-1Team/ai
    python3 compare_models.py out/cmp_4o_1.json out/cmp_5_1.json ...
"""
import json
import sys
from pathlib import Path

FIX = "tests/fixtures/meeting_note_1_complete.md"
SOURCE = Path(FIX).read_text(encoding="utf-8") if Path(FIX).exists() else ""

# 팀원 기획서에는 있는데 우리가 놓친 것들
TARGETS = {
    "ZXing 작업량(2~3일)": ["2~3일", "2-3일"],
    "BarcodeDetector": ["barcodedetector"],
    "POS A사 API": ["pos"],
    "Next.js 미채택": ["next.js"],
}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def scorecard(data):
    reqs = data.get("requirements") or {}
    project = data.get("project") or {}
    out = {}

    # ── 회수율 ───────────────────────────────────────────────
    for key in ("functional", "non_functional", "data", "technical"):
        out[f"req.{key}"] = len(reqs.get(key) or [])
    out["constraints"] = len(data.get("constraints") or [])
    out["decisions"] = len(data.get("decisions") or [])
    out["goals"] = len(project.get("goals") or [])
    out["problem_items"] = len(project.get("problem_items") or [])
    out["users.needs 합계"] = sum(
        len(u.get("needs") or []) for u in (data.get("users") or [])
    )
    out["기능(feature_name) 수"] = len({
        i.get("feature_name")
        for i in (reqs.get("functional") or [])
        if i.get("feature_name")
    })

    # ── 타깃 항목 확보 여부 ──────────────────────────────────
    pool = " ".join(
        str(i.get("content", ""))
        for group in ("technical", "non_functional", "data", "functional")
        for i in (reqs.get(group) or [])
    ).lower()
    pool += " " + " ".join(
        str(c.get("content", "")) for c in (data.get("constraints") or [])
    ).lower()

    for label, keys in TARGETS.items():
        out[f"※ {label}"] = "O" if any(k in pool for k in keys) else "-"

    # ── 정확성 ───────────────────────────────────────────────
    total = verified = 0

    def walk(node):
        nonlocal total, verified
        if isinstance(node, dict):
            if "evidence_status" in node:
                total += 1
                verified += node["evidence_status"] == "verified"
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    out["근거 verified"] = f"{verified}/{total}"

    # 결정 분류: 구현 방식이 tech로 갔는가
    bad = 0
    for d in data.get("decisions") or []:
        c = str(d.get("content", "")).lower()
        if ("barcodedetector" in c or "웹 카메라" in c) and d.get("category") != "tech":
            bad += 1
    out["결정 분류 오류"] = bad

    # background 수치 보존
    bg = str(project.get("background", ""))
    out["개요 수치 보존"] = "O" if ("12" in bg and "11" in bg) else "-"

    # 창작 감시: quote로 대조되지 않는 추상어
    ABSTRACT = ["효율성", "편의성", "자동화", "최적화", "도입 장벽"]
    hits = [w for w in ABSTRACT if w in bg or any(
        w in n for u in (data.get("users") or []) for n in (u.get("needs") or [])
    )]
    out["추상어 혼입"] = ",".join(hits) if hits else "-"

    return out


def main():
    paths = sys.argv[1:]
    if not paths:
        print(__doc__)
        raise SystemExit(1)

    cards = [(Path(p).stem, scorecard(load(p))) for p in paths]
    keys = list(cards[0][1].keys())

    w = max(len(k) for k in keys) + 2
    header = "항목".ljust(w) + "".join(n[:14].rjust(16) for n, _ in cards)
    print(header)
    print("-" * len(header))
    for k in keys:
        row = k.ljust(w) + "".join(str(c[k])[:14].rjust(16) for _, c in cards)
        print(row)

    print("\n※ 표시는 팀원 기획서에는 있고 우리가 놓쳤던 항목입니다.")
    print("회수율이 올라도 '추상어 혼입'과 '근거 verified'가 나빠지면 손해입니다.")


if __name__ == "__main__":
    main()
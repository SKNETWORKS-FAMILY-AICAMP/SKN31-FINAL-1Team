"""
변경 전후 추출 결과를 항목 단위로 대조합니다. LLM을 호출하지 않습니다.

건수만 보면 "데이터 1 -> 0"처럼 줄어든 사실만 알 뿐,
무엇이 사라졌는지 모르기 때문에 원인을 판단할 수 없습니다.
이 스크립트는 사라진 항목과 새로 생긴 항목을 내용으로 보여줍니다.

사용법:
    cd ~/projects/SKN31-FINAL-1Team/ai
    python3 compare_eval.py                          # before <-> out
    python3 compare_eval.py eval_baseline/after       # before <-> after
    python3 compare_eval.py out meeting_note_1_complete   # 한 회의록만
"""
import difflib
import json
import sys
from pathlib import Path

BEFORE_DIR = Path("eval_baseline/before")
AFTER_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("out")
ONLY = sys.argv[2] if len(sys.argv) > 2 else None

STEMS = [
    "meeting_note_1_complete",
    "meeting_note_2_vague",
    "meeting_note_3_long",
    "meeting_note_4_scenario",
    "meeting_note_5_unseen",
]

# (표시 이름, JSON 경로)
FIELDS = [
    ("목표", ("project", "goals")),
    ("문제", ("project", "problem_items")),
    ("사용자", ("users",)),
    ("기능", ("requirements", "functional")),
    ("비기능", ("requirements", "non_functional")),
    ("데이터", ("requirements", "data")),
    ("기술", ("requirements", "technical")),
    ("시나리오", ("scenarios",)),
    ("결정", ("decisions",)),
    ("제약", ("constraints",)),
    ("미해결", ("unresolved",)),
]


def dig(data, path):
    node = data
    for key in path:
        if not isinstance(node, dict):
            return []
        node = node.get(key)
    return node if isinstance(node, list) else []


def label(item) -> str:
    """항목을 사람이 알아볼 문자열로 만든다."""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for key in ("content", "type", "title", "name"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return str(item)[:60]


def key_of(text: str) -> str:
    """표현이 조금 달라도 같은 항목으로 보기 위한 정규화."""
    return "".join(ch for ch in text if ch.isalnum()).lower()


# 같은 항목으로 볼 유사도 기준.
# "바코드 입출고 등록 기능을 제공한다"와 "바코드 입출고 등록 기능 제공"은
# 같은 항목인데 문자열이 달라서, 그대로 비교하면 사라짐과 새로생김이
# 동시에 찍혀 진짜 변화를 가립니다.
SAME_ITEM_RATIO = 0.72


def match_items(old_texts, new_texts):
    """이전/이후 항목을 짝지어 사라짐·새로생김·표현변화로 나눈다."""
    old_keys = [key_of(t) for t in old_texts]
    new_keys = [key_of(t) for t in new_texts]

    used_new: set[int] = set()
    removed: list[str] = []
    reworded: list[tuple[str, str]] = []

    for i, old_key in enumerate(old_keys):
        best_index = -1
        best_ratio = 0.0

        for j, new_key in enumerate(new_keys):
            if j in used_new:
                continue

            if old_key == new_key:
                best_index, best_ratio = j, 1.0
                break

            ratio = difflib.SequenceMatcher(
                None, old_key, new_key
            ).ratio()

            if ratio > best_ratio:
                best_index, best_ratio = j, ratio

        if best_index >= 0 and best_ratio >= SAME_ITEM_RATIO:
            used_new.add(best_index)
            if best_ratio < 1.0:
                reworded.append(
                    (old_texts[i], new_texts[best_index])
                )
        else:
            removed.append(old_texts[i])

    added = [
        new_texts[j]
        for j in range(len(new_texts))
        if j not in used_new
    ]
    return removed, added, reworded


def compare(stem: str) -> None:
    before_path = BEFORE_DIR / f"{stem}.json"
    after_path = AFTER_DIR / f"{stem}.json"

    if not before_path.exists() or not after_path.exists():
        missing = "이전" if not before_path.exists() else "이후"
        print(f"\n### {stem} — {missing} 파일이 없어 건너뜁니다")
        return

    before = json.loads(before_path.read_text(encoding="utf-8"))
    after = json.loads(after_path.read_text(encoding="utf-8"))

    lines: list[str] = []

    for name, path in FIELDS:
        old_texts = [label(x) for x in dig(before, path)]
        new_texts = [label(x) for x in dig(after, path)]

        removed, added, reworded = match_items(old_texts, new_texts)

        if not removed and not added and not reworded:
            continue

        lines.append(
            f"\n  [{name}] {len(old_texts)} -> {len(new_texts)}"
        )
        for text in removed:
            lines.append(f"    - 사라짐   : {text[:74]}")
        for text in added:
            lines.append(f"    + 새로생김 : {text[:74]}")
        for old_text, new_text in reworded:
            lines.append(f"    ~ 표현만바뀜: {old_text[:36]}  ->  {new_text[:36]}")

    # 근거 검증 상태 변화
    def unverified(data):
        found = []

        def walk(node, path=""):
            if isinstance(node, dict):
                if node.get("evidence_status") == "unverified":
                    found.append((path, label(node)))
                for k, v in node.items():
                    walk(v, f"{path}.{k}" if path else k)
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, f"{path}[{i}]")

        walk(data)
        return found

    old_bad = unverified(before)
    new_bad = unverified(after)

    if old_bad or new_bad:
        lines.append(
            f"\n  [근거 미검증] {len(old_bad)}건 -> {len(new_bad)}건"
        )
        old_keys = {key_of(t) for _, t in old_bad}
        for path, text in new_bad:
            mark = "계속" if key_of(text) in old_keys else "새로"
            lines.append(f"    {mark} {path} : {text[:66]}")

    print(f"\n### {stem}")
    if lines:
        print("\n".join(lines))
    else:
        print("  변화 없음")


print(f"이전: {BEFORE_DIR}    이후: {AFTER_DIR}")
print("=" * 78)

for stem in STEMS:
    if ONLY and stem != ONLY:
        continue
    compare(stem)

print("\n" + "=" * 78)
print("읽는 법")
print("  사라진 항목이 프롬프트에서 지운 예시와 같은 내용이면")
print("    -> 예시를 보고 적던 것이므로 부풀림이 빠진 것입니다. 고칠 게 없습니다.")
print("  사라진 항목이 지운 예시와 무관하면")
print("    -> 프롬프트가 길어져 생긴 손실일 수 있습니다. 규칙을 줄여 재측정하세요.")
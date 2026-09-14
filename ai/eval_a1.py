"""
A1 영역(회의록 구조화) 평가 측정.

표준 회의록을 3회 반복해 실행 간 변동폭을 재고,
성격이 다른 회의록 3종을 1회씩 돌려 일반화 가능성을 본다.

사용법:
    cd ~/projects/SKN31-FINAL-1Team/ai
    python3 eval_a1.py              # 기본: 표준 3회 + 다른 회의록 3종
    python3 eval_a1.py 2            # 표준 2회로 줄이기
"""
import json
import subprocess
import sys
from pathlib import Path

REPEAT = int(sys.argv[1]) if len(sys.argv) > 1 else 3
STANDARD = "meeting_note_1_complete"
OTHERS = ["meeting_note_2_vague", "meeting_note_3_long", "meeting_note_4_scenario"]

# 프롬프트 예시와 도메인이 겹치지 않는 회의록입니다.
# 위 4개는 전부 재고·발주 도메인이라 점수가 실제보다 높게 나올 수 있습니다.
# 이 회의록은 프롬프트가 본 적 없는 어휘로만 쓰여 있어,
# 여기 점수가 일반화 가능성에 더 가깝습니다.
UNSEEN = ["meeting_note_5_unseen"]


def run_node(stem: str) -> dict | None:
    """노드1을 실행하고 결과 JSON을 읽는다."""
    path = Path("tests/fixtures") / f"{stem}.md"
    if not path.exists():
        print(f"  건너뜀 — {path} 없음")
        return None

    proc = subprocess.run(
        [sys.executable, "-m", "meeting_analysis.node", str(path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print(f"  실행 실패 — {proc.stderr.strip().splitlines()[-1][:70]}")
        return None

    out = Path("out") / f"{stem}.json"
    return json.loads(out.read_text(encoding="utf-8"))


# 목적만 밝히고 이유를 말하지 않는 어미입니다.
_PURPOSE_ENDINGS = ("위함", "위해서", "위하여", "목적", "위함.", "위해")


def needs_reason_review(decision: dict) -> bool:
    """rationale을 사람이 확인해야 하는지 표시한다.

    ## 왜 자동으로 판정하지 않는가

    처음에는 rationale과 결정 내용의 어절 겹침을 계산해 동어반복을
    자동 판정하려 했습니다. 실제 출력 15건에 라벨을 붙여 재보니
    6건 중 2건만 잡았습니다(오탐 0, 놓침 4).

    실패한 이유는 겹침이 잘못된 신호이기 때문입니다.
    "상품별로 적절한 재고 임계치를 설정하기 위함"은 결정 내용과
    겹치는 말이 적은데도 이유를 말하지 않습니다. 반대로
    "알림톡이 문자보다 단가가 낮고 ... 비용을 절감하기 위함"은
    겹침과 무관하게 회의에서 나온 진짜 이유입니다.

    구분하려면 "이 문장이 결정 밖의 사실을 담고 있는가"를 알아야
    하는데, 이건 의미 판단이라 규칙으로 안 됩니다.

    ## 그래서 지금 방식

    목적형 어미로 끝나는 것만 표시하고 판정은 사람이 합니다.
    15건 기준으로 8건이 표시되고 그 안에 동어반복 6건이 모두
    들어갑니다. 놓치는 것 없이 확인할 양을 절반으로 줄입니다.

    보고서에는 이 숫자가 아니라 육안 확인 결과를 씁니다.
    """
    reason = str(decision.get("rationale") or "").strip()

    if not reason:
        return False

    return reason.rstrip(".").endswith(_PURPOSE_ENDINGS)


def measure(d: dict) -> dict:
    """지표를 집계한다."""
    project = d.get("project") or {}
    reqs = d.get("requirements") or {}
    dec = d.get("decisions") or []

    # 근거 검증 — 배열 항목의 evidence_status + 프로젝트 수준 2건
    total = verified = 0

    def walk(n):
        nonlocal total, verified
        if isinstance(n, dict):
            if "evidence_status" in n:
                total += 1
                verified += n["evidence_status"] == "verified"
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(d)
    for key in ("background_evidence_status", "problem_evidence_status"):
        if key in project:
            total += 1
            verified += project[key] == "verified"

    has_reason = sum(1 for x in dec if str(x.get("rationale") or "").strip())

    # rationale이 결정 내용을 되풀이한 것인지 의심되는 건수.
    #
    # ※ 자동 판정은 부정확합니다. 한국어 조사·어미 때문에 겹침 계산이
    #   빗나가고, "필요한 정보를 포함하기 위함"처럼 겹침은 낮지만
    #   내용이 없는 문장도 있습니다. 그래서 이 값은 지표가 아니라
    #   "사람이 확인할 목록"입니다. 보고서에는 육안 확인한 수를 씁니다.
    review_needed = [x for x in dec if needs_reason_review(x)]

    # 구현 방식 결정이 tech로 갔는지
    misclassified = sum(
        1 for x in dec
        if ("barcodedetector" in str(x.get("content", "")).lower()
            or "웹 카메라" in str(x.get("content", "")))
        and x.get("category") != "tech"
    )

    return {
        "근거": f"{verified}/{total}",
        "근거%": round(verified / total * 100) if total else 0,
        "사유": f"{has_reason}/{len(dec)}",
        "사유%": round(has_reason / len(dec) * 100) if dec else 0,
        "사유확인": len(review_needed),
        "_확인목록": [
            (str(x.get("content", ""))[:40], str(x.get("rationale", ""))[:44])
            for x in review_needed
        ],
        "분류오류": misclassified,
        "기능": len(reqs.get("functional") or []),
        "비기능": len(reqs.get("non_functional") or []),
        "데이터": len(reqs.get("data") or []),
        "기술": len(reqs.get("technical") or []),
        "제약": len(d.get("constraints") or []),
        "결정": len(dec),
        "목표": len(project.get("goals") or []),
        "문제": len(project.get("problem_items") or []),
    }


COLS = ["근거%", "사유%", "사유확인", "분류오류", "기능", "비기능", "데이터", "기술", "제약", "결정", "목표", "문제"]


def show(title, rows):
    print(f"\n{title}")
    print("─" * 78)
    print(f"{'실행':<22}" + "".join(c.rjust(7) for c in COLS))
    for name, m in rows:
        print(f"{name:<22}" + "".join(str(m[c]).rjust(7) for c in COLS))


print(
    f"표준 {REPEAT}회 + 같은 도메인 {len(OTHERS)}종 + 미학습 도메인 {len(UNSEEN)}종"
    f" — LLM {REPEAT + len(OTHERS) + len(UNSEEN)}회 호출"
)

repeats = []
for i in range(REPEAT):
    print(f"\n[{i+1}/{REPEAT}] {STANDARD}")
    d = run_node(STANDARD)
    if d:
        repeats.append((f"{STANDARD[:14]} #{i+1}", measure(d)))

others = []
for stem in OTHERS:
    print(f"\n[{stem}]")
    d = run_node(stem)
    if d:
        others.append((stem[:22], measure(d)))

if repeats:
    show("⑥ 실행 간 변동폭 — 같은 회의록 반복", repeats)
    print("\n  변동폭:")
    for c in COLS:
        vals = [m[c] for _, m in repeats]
        if max(vals) != min(vals):
            print(f"    {c}: {min(vals)} ~ {max(vals)}  (폭 {max(vals)-min(vals)})")
    if all(max(m[c] for _, m in repeats) == min(m[c] for _, m in repeats) for c in COLS):
        print("    변동 없음")

unseen = []
for stem in UNSEEN:
    print(f"\n[{stem}] — 미학습 도메인")
    d = run_node(stem)
    if d:
        unseen.append((stem[:22], measure(d)))

if others:
    show("⑨ 다른 성격의 회의록 (같은 도메인)", others)

if unseen:
    show("⑩ 미학습 도메인 — 프롬프트 예시와 어휘가 겹치지 않음", unseen)
    print("\n  위 4개와 점수 차이가 크면 기존 숫자가 도메인 덕을 본 것입니다.")

print("\n" + "─" * 78)
print("게이트 지표 확인")
allr = repeats + others
if allr:
    bad = [n for n, m in allr if m["근거%"] != 100]
    print(f"  근거 검증 100% 미달  : {len(bad)}건" + (f" — {bad}" if bad else ""))
    bad2 = [n for n, m in allr if m["분류오류"] > 0]
    print(f"  구현 방식 분류 오류  : {len(bad2)}건" + (f" — {bad2}" if bad2 else ""))
susp = [(n, m) for n, m in (repeats + others + unseen) if m["사유확인"]]
if susp:
    print("\n" + "─" * 78)
    print("사유 확인 목록 — 목적형 어미로 끝나는 rationale입니다")
    print("  결정 내용을 바꿔 쓴 것이면 실질 사유에서 빼고 세십시오.")
    print("  회의에서 나온 이유를 담고 있으면 그대로 인정합니다.")
    for name, m in susp:
        print(f"\n  [{name}] {m['사유확인']}건")
        for content, reason in m["_확인목록"]:
            print(f"    결정: {content}")
            print(f"    사유: {reason}")

print("\nvague 회의록은 '정보가 없을 때 지어내지 않는가'를 보는 케이스입니다.")
print("추출 건수가 표준 회의록보다 적은 것이 정상입니다.")
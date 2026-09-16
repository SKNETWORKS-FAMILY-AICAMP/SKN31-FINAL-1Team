"""
[2] Evidence 원문 검증 — 보존 방식.

evidence.quote가 회의록 원문에 실재하는지 코드로 검사합니다.

## 삭제하지 않고 보존하는 이유

evidence 매칭 실패에는 두 가지 원인이 있습니다.

  경우 A — LLM이 회의록에 없는 내용을 만들어냈다 (진짜 할루시네이션)
  경우 B — 내용은 회의록에 있는데 인용할 때 어미·조사를 바꿨다 (매칭 문제)

두 경우를 코드가 구분할 수 없습니다. 그래서 삭제하면 경우 B의
멀쩡한 정보까지 사라집니다. 보존해두면 나중에 필터로 걸러낼 수
있지만, 삭제한 것은 되돌릴 수 없습니다.

## unresolved와 구분

  unresolved                 = 회의에서 논의되지 않아 정보 자체가 없음
  evidence_status=unverified = 추출은 했는데 근거 확인 실패

두 개를 같은 곳에 넣지 않습니다.

※ 이 모듈은 절대 LLM을 호출하지 않습니다.
  "근거를 다시 찾아봐"라고 시키면 모델은 더 그럴듯한 인용을 만들어냅니다.
"""

import difflib
import re
from dataclasses import dataclass, field

# evidence를 가진 항목들이 들어 있는 경로.
# project는 단일 객체라 별도 처리합니다.
ARRAY_PATHS = [
    "project.problem_items",
    "project.goals",
    "users",
    "requirements.functional",
    "requirements.non_functional",
    "requirements.data",
    "requirements.technical",
    "scenarios",
    "decisions",
    "constraints",
]

# 정규화 시 제거할 문장부호.
# ※ 미확정 — 실행 결과에서 오탐(멀쩡한 항목이 unverified)/미탐 비율을
#   보고 조정하세요. 지금 값은 출발점일 뿐입니다.
_PUNCT = r"[.,!?~·…\"'\u201c\u201d\u2018\u2019()\[\]{}:;\-]"

VERIFIED = "verified"
UNVERIFIED = "unverified"

# 2차 매칭(유사도) 통과 기준. normalize()로 공백·문장부호를 지운 뒤
# 비교합니다. 2026-09-16: 실측(실제 회의록 재실행)에서 노드 1이 원문
# "깔끔하게"를 근거 quote에 "깔끗하게"로 한 글자 잘못 옮겨 적어, 내용은
# 맞게 뽑았는데도 이 결정 하나가 unverified로 빠지고 하류(plan_draft)에서
# 조용히 사라지는 사례를 확인했습니다. 이런 한두 글자 오차(경우 B)까지
# 구제하되, 완전히 다른 문장(경우 A, 진짜 할루시네이션)은 걸러야 하므로
# 임계값을 보수적으로 높게 잡았습니다. 오탐(지어낸 내용이 통과)이
# 보이면 올리고, 미탐(멀쩡한 인용이 계속 unverified)이 보이면 내리세요.
_SIMILARITY_THRESHOLD = 0.92


def normalize(text: str) -> str:
    """
    비교 전 정규화.

    LLM은 인용할 때 공백이나 문장부호를 미묘하게 바꾸는 일이 잦습니다.
    ("텍스트 방식으로 입력한다." -> "텍스트방식으로 입력한다")
    이 차이로 매칭이 깨지면 멀쩡한 항목이 unverified가 되므로
    양쪽을 같은 방식으로 정규화합니다.
    """
    text = re.sub(r"\s+", "", text)
    text = re.sub(_PUNCT, "", text)
    return text


@dataclass
class UnverifiedItem:
    """근거 확인에 실패한 항목의 기록. 삭제 대상이 아닙니다."""
    path: str      # 예: "requirements.functional[2]"
    content: str   # 항목 내용 (원인 A/B 판단용)
    quote: str     # LLM이 근거로 든 문장 (원문과 대조해볼 것)


@dataclass
class EvidenceReport:
    unverified: list[UnverifiedItem] = field(default_factory=list)
    checked: int = 0

    @property
    def verified_count(self) -> int:
        return self.checked - len(self.unverified)

    @property
    def pass_rate(self) -> float:
        if self.checked == 0:
            return 1.0
        return self.verified_count / self.checked


def _fuzzy_verified(quote: str, source: str) -> bool:
    """
    quote가 source 어딘가와 근사 일치하는지 봅니다. 둘 다 normalize()를
    거친 문자열이어야 합니다.

    source 전체와 quote를 통째로 비교하면(O(n*m)) 회의록 길이에서 느려질
    뿐 아니라, source 여기저기 흩어진 글자들이 우연히 겹쳐 실제로는
    존재하지 않는 내용을 통과시킬 위험도 있습니다. 대신 먼저 최장 공통
    부분열로 source에서 quote와 제일 겹치는 위치를 찾고, 그 주변
    (quote 길이만큼)만 잘라내 그 구간과만 유사도를 비교합니다 — 실제로
    한 곳에 뭉쳐 있는 인용만 통과시키기 위해서입니다.
    """
    if not quote:
        return False

    matcher = difflib.SequenceMatcher(None, source, quote, autojunk=False)
    match = matcher.find_longest_match(0, len(source), 0, len(quote))

    if match.size == 0:
        return False

    window_start = max(0, match.a - match.b)
    window_end = min(len(source), window_start + len(quote) + 10)
    window = source[window_start:window_end]

    ratio = difflib.SequenceMatcher(None, window, quote, autojunk=False).ratio()
    return ratio >= _SIMILARITY_THRESHOLD


def _get(data: dict, path: str):
    """'requirements.functional' 같은 점 경로로 값을 꺼냅니다."""
    cur = data
    for part in path.split("."):
        cur = cur.get(part) if isinstance(cur, dict) else None
        if cur is None:
            return None
    return cur


def verify_and_mark(data: dict, meeting_raw_text: str) -> EvidenceReport:
    """
    검사하고 각 항목에 evidence_status를 붙입니다.
    항목을 제거하지 않습니다.

    반환하는 리포트는 통과율 집계와 실패 원인 분석에 씁니다.
    """
    report = EvidenceReport()
    source = normalize(meeting_raw_text)

    def check(
        item: dict, path: str, content: str,
        evidence_key: str = "evidence", status_key: str = "evidence_status",
    ) -> None:
        quote = (item.get(evidence_key) or {}).get("quote", "")
        report.checked += 1

        # 1차: 정규화 후 부분 문자열 매칭
        normalized_quote = normalize(quote)
        if quote and normalized_quote in source:
            item[status_key] = VERIFIED
            return

        # 2차: 유사도 매칭
        # 어미·조사가 바뀌거나 한두 글자를 잘못 옮겨 적은 인용(경우 B)을
        # 구제합니다. _fuzzy_verified 참고.
        if quote and _fuzzy_verified(normalized_quote, source):
            item[status_key] = VERIFIED
            return

        item[status_key] = UNVERIFIED
        report.unverified.append(
            UnverifiedItem(path=path, content=content, quote=quote)
        )

    # project (단일 객체)
    #
    # 2026-09-07: evidence가 background_evidence/problem_evidence로 나뉘면서
    # 각각 따로 검증합니다. 예전엔 project에 evidence 하나만 있어서 한 번만
    # 검사했지만, 이제 project는 evidence를 두 개 갖고 있으므로 검사도
    # 두 번 하고 상태도 각자의 status_key(background_evidence_status /
    # problem_evidence_status)에 따로 붙입니다.
    project = data.get("project")
    if project:
        check(
            project, "project.background", project.get("background", ""),
            evidence_key="background_evidence",
            status_key="background_evidence_status",
        )
        check(
            project, "project.problem", project.get("problem", ""),
            evidence_key="problem_evidence",
            status_key="problem_evidence_status",
        )

    # 배열 영역
    for base in ARRAY_PATHS:
        items = _get(data, base) or []
        for idx, item in enumerate(items):
            content = item.get("content") or item.get("type", "")
            check(item, f"{base}[{idx}]", content)

    return report


def format_report(report: EvidenceReport) -> str:
    """
    실행 결과 확인용 리포트.

    unverified 항목은 원인을 두 가지로 구분해야 합니다.
      경우 A — quote가 회의록에 정말 없음 → 모델이 지어냄
      경우 B — 회의록에 있는데 어미만 다름 → 정규화 문제
    아래 출력의 quote를 회의록에서 직접 찾아보고 판단하세요.
    """
    lines = [
        f"Evidence 통과율 : {report.pass_rate:.1%} "
        f"({report.verified_count}/{report.checked})"
    ]
    if report.unverified:
        lines.append(f"\n근거 미확인 항목 {len(report.unverified)}건 "
                     "(삭제되지 않고 보존됨):")
        for u in report.unverified:
            lines.append(f"  · [{u.path}] {u.content[:40]}")
            lines.append(f"      quote: \"{u.quote[:60]}\"")
        lines.append("\n  ↑ 위 quote를 회의록에서 직접 찾아보세요.")
        lines.append("     정말 없으면 → 모델이 지어냄 (프롬프트 문제)")
        lines.append("     있는데 어미만 다르면 → 정규화 문제 (_PUNCT 조정)")
    return "\n".join(lines)
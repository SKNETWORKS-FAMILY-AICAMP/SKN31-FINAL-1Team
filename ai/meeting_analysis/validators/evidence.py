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

# 2026-09-16: 유사도만으로는 부정어 하나 차이를 못 잡습니다. 실측(Codex
# 재현)에서 "외부 서버에 전송하지 않는다"의 "하지 않"만 지운 "전송한다"가
# 문장이 길수록(70자 이상) 편집거리 비중이 작아져 ratio 0.96까지 나와
# verified로 통과했습니다 — 뜻이 반대인데 근거로 인정되는 심각한 오탐입니다.
#
# 완벽한 해법은 의미 이해(LLM 재확인)뿐인데, 그건 이 모듈이 절대 LLM을
# 부르지 않는다는 원칙(모듈 docstring 참고)에 어긋납니다. 대신 한국어
# 부정 표현 중 다른 단어에 잘 안 섞이는 것들(있다/없다의 "없", "-지
# 않다"의 "않", "못하다"의 "못")의 등장 횟수가 quote와 source 구간에서
# 다르면, ratio가 아무리 높아도 무조건 거부합니다. "안"과 "아니"는
# "제안", "방안"처럼 무관한 단어에 흔히 섞여 있어 오탐이 너무 많을
# 것으로 보여 제외했습니다 — 이 셋만으로는 모든 부정 표현을 못 잡지만
# (예: "안 한다"), 실측된 사례는 잡습니다.
_NEGATION_MARKERS = ("않", "없", "못")


def _negation_signature(text: str) -> tuple[int, ...]:
    """부정 표현 등장 횟수를 센 서명. 다르면 의미가 반대일 가능성이 큽니다."""
    return tuple(text.count(marker) for marker in _NEGATION_MARKERS)


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

    if _negation_signature(window) != _negation_signature(quote):
        return False

    ratio = difflib.SequenceMatcher(None, window, quote, autojunk=False).ratio()
    return ratio >= _SIMILARITY_THRESHOLD


def is_quote_verified(quote: str, source_text: str) -> bool:
    """
    quote가 source_text(원문, 정규화 전) 안에서 확인되는지 반환합니다.

    verify_and_mark()의 검사 로직(정규화 후 부분 문자열 매칭 → 실패하면
    유사도 매칭)을 그대로 재사용할 수 있게 뽑아냈습니다. 노드①의 구조화
    항목 전체를 훑는 verify_and_mark()와 달리, 인용문 하나만 원문과
    대조하면 되는 호출부(예: plan_draft.fact_check — 완성된 기획서
    문장이 회의록과 모순되는지 검토할 때, LLM이 댄 인용을 그대로
    믿지 않고 원문에 실제 있는지 다시 확인)를 위한 것입니다.

    같은 검증 로직을 호출부마다 다시 구현하면 기준이 갈릴 위험이
    있습니다(_evidence_key 관련 주석 — plan_draft/list_builder.py —
    참고). 새로 근거를 검증해야 하는 곳은 이 함수를 재사용하세요.
    """
    if not quote or not quote.strip():
        return False

    source = normalize(source_text)
    normalized_quote = normalize(quote)

    if normalized_quote and normalized_quote in source:
        return True

    return _fuzzy_verified(normalized_quote, source)


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

    def check(
        item: dict, path: str, content: str,
        evidence_key: str = "evidence", status_key: str = "evidence_status",
    ) -> None:
        quote = (item.get(evidence_key) or {}).get("quote", "")
        report.checked += 1

        if is_quote_verified(quote, meeting_raw_text):
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
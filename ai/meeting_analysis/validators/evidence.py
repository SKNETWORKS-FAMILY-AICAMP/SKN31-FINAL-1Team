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

import re
from dataclasses import dataclass, field

# evidence를 가진 항목들이 들어 있는 경로.
# project는 단일 객체라 별도 처리합니다.
ARRAY_PATHS = [
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

    def check(item: dict, path: str, content: str) -> None:
        quote = (item.get("evidence") or {}).get("quote", "")
        report.checked += 1

        # 1차: 정규화 후 부분 문자열 매칭
        if quote and normalize(quote) in source:
            item["evidence_status"] = VERIFIED
            return

        # 2차: 유사도 매칭 (미도입)
        # 어미·조사가 바뀐 인용(경우 B)을 구제하기 위한 안전장치입니다.
        # 알고리즘과 임계값 모두 미확정이므로 일단 끕니다.
        # 1차만으로 몇 %가 걸러지는지 실측한 뒤 도입 여부를 정하세요.
        # if similarity(quote, meeting_raw_text) >= THRESHOLD:
        #     item["evidence_status"] = VERIFIED
        #     return

        item["evidence_status"] = UNVERIFIED
        report.unverified.append(
            UnverifiedItem(path=path, content=content, quote=quote)
        )

    # project (단일 객체)
    project = data.get("project")
    if project:
        check(project, "project", project.get("problem", ""))

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

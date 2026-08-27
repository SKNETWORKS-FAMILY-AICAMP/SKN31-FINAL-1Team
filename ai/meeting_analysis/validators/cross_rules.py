"""
[4] 교차 규칙 검증.

Pydantic이 못 잡는 '필드 간' 정합성을 검사합니다.
각 필드는 유효한데 조합이 이상한 경우를 찾습니다.

※ 왜 evidence 처리 뒤에 두는가:
  [2]에서 항목이 제거되면 데이터 구성이 달라집니다.
  제거 전 상태로 검사하면 곧 사라질 항목을 기준으로 판정하게 되고,
  제거 후에 새로 생긴 불일치를 놓칩니다.
  (예: 기술 결정은 남았는데 대응하는 technical 요구사항이 제거된 경우)
  최종 저장될 상태를 기준으로 검사해야 합니다.

※ 위반해도 LLM을 재호출하지 않습니다.
  notes에 기록해 PM에게 알리는 것까지가 이 단계의 역할입니다.

※ 아래 규칙 3개는 예시입니다.
  실제 규칙 목록은 시범 실행 결과를 보고 확정하세요.
"""

from .evidence import normalize

REQ_CATEGORIES = ["functional", "non_functional", "data", "technical"]

# 임계값. 임의로 잡은 값이므로 실측 후 조정하세요.
MAX_ITEMS_PER_CATEGORY = 20


def check(data: dict) -> list[str]:
    """위반 사항을 문자열 리스트로 반환합니다."""
    notes: list[str] = []
    reqs = data.get("requirements", {})

    # 규칙 1: 기술 결정이 있는데 기술 요구사항이 비어 있는가
    tech_decisions = [
        d for d in data.get("decisions", []) if d.get("category") == "tech"
    ]
    if tech_decisions and not reqs.get("technical"):
        notes.append(
            "기술 관련 결정사항이 있으나 기술 요구사항이 비어 있습니다. 확인이 필요합니다."
        )

    # 규칙 2: 같은 내용이 여러 분류에 중복 등록됐는가
    seen: dict[str, str] = {}
    for category in REQ_CATEGORIES:
        for item in reqs.get(category, []):
            key = normalize(item.get("content", ""))
            if not key:
                continue
            if key in seen and seen[key] != category:
                notes.append(
                    f"동일 내용이 {seen[key]}와 {category}에 중복 등록됐습니다: "
                    f"{item['content'][:25]}"
                )
            seen[key] = category

    # 규칙 3: 항목 수가 비정상적으로 많은가 (프롬프트 폭주 신호)
    for category in REQ_CATEGORIES:
        count = len(reqs.get(category, []))
        if count > MAX_ITEMS_PER_CATEGORY:
            notes.append(
                f"{category} 요구사항이 {count}건으로 비정상적으로 많습니다. "
                "프롬프트나 회의록 길이를 확인하세요."
            )

    return notes

"""
[3] 교차 규칙 검증.

Pydantic이 못 잡는 '필드 간' 정합성을 검사합니다.
각 필드는 유효한데 조합이 이상한 경우를 찾습니다.

※ Evidence 검증 뒤에 실행합니다.
  항목에 evidence_status가 붙은 최종 상태를 기준으로 검사해야 실제 저장될 데이터의 정합성을 봅니다.

※ LLM을 호출하지 않습니다.
    여기서 하는 판정은 전부 len()으로 확인되는 사실입니다.
    "non_functional에 항목이 있나?"는  세면 되는 일이지 모델에게 물어볼 일이 아닙니다.

"""

from .evidence import normalize

REQ_CATEGORIES = ["functional", "non_functional", "data", "technical"]

# 항목 수가 이보다 많으면 프롬프트 폭주를 의심합니다.
# 임계값. 임의로 잡은 값이므로 실측 후 조정하세요.
MAX_ITEMS_PER_CATEGORY = 20

# unresolved 문구가 어느 영역을 지목하는지 판정할 키워드.
# 모델이 "비기능 요구사항이 논의되지 않았습니다."라고 썼는데
# non_functiona에 항목이 있으면 모순입니다.
AREA_KEYWORDS = {
    "requirements.non_functional": ["성능", "응답 속도", "동시 접속"],
    "requirements.technical": ["기술 스택", "기술스택", "기술 요구"],
    "requirements.data": ["데이터"],
    "requirements.functional": ["기능 요구사항"],
    "scenarios": ["시나리오"],
    "users": ["대상 사용자", "사용자 정의"],
    "constraints": ["제약"],
}


def _get_items(data: dict, path: str) -> list:
    """'requirements.non_functional' 또는 'scenarios' 경로로 배열을 꺼냅니다."""
    if "." in path:
        base, sub = path.split(".", 1)
        return (data.get(base) or {}).get(sub) or []
    return data.get(path) or []
 
 
def check_unresolved_consistency(data: dict) -> list[str]:
    """
    unresolved 모순 검사 — 이 모듈에서 유일하게 데이터를 수정합니다.
 
    ## 왜 필요한가
 
    긴 회의록에서 모델이 실제 추출 결과와 무관하게 unresolved를 씁니다.
    자기가 non_functional 항목을 뽑아놓고
    "비기능 요구사항이 논의되지 않았습니다"라고 적는 식입니다.
 
    unresolved는 PM이 "회의에서 이건 안 정했구나"를 판단하는 근거입니다.
    거짓이면 논의된 내용이 묻히므로, 없는 걸 지어내는 것만큼 나쁩니다.
 
    ## 왜 제거까지 하는가
 
    다른 규칙은 기록만 하는데 이것만 데이터를 고칩니다.
    모순된 unresolved를 남겨두면 PM이 그대로 읽고 잘못 판단하기 때문입니다.
    제거 사실은 notes에 남으므로 추적은 가능합니다.
    """
    kept: list[str] = []
    notes: list[str] = []
 
    for u in data.get("unresolved", []):
        contradiction = None
 
        for path, keywords in AREA_KEYWORDS.items():
            if not any(k in u for k in keywords):
                continue
            items = _get_items(data, path)
            if items:
                contradiction = (path, len(items))
                break
 
        if contradiction:
            path, count = contradiction
            notes.append(
                f"unresolved 항목을 제거했습니다: \"{u[:35]}...\" — "
                f"{path}에 실제로 {count}건이 추출되어 있어 모순입니다."
            )
        else:
            kept.append(u)
 
    data["unresolved"] = kept
    return notes
 
 
def check(data: dict) -> list[str]:
    """
    교차 규칙 전체.
    반환값은 validation_notes에 담깁니다.
 
    ※ 아래 규칙 3개는 예시입니다.
      실제 목록은 회의록을 더 돌려보고 확정하세요.
    """
    notes: list[str] = []
    reqs = data.get("requirements", {})
 
    # ── unresolved 모순 검사 (데이터 수정 있음) ──────────────
    notes += check_unresolved_consistency(data)
 
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
 
   
 
    # 규칙 4: 항목 수가 비정상적으로 많은가 (프롬프트 폭주 신호)
    for category in REQ_CATEGORIES:
        count = len(reqs.get(category, []))
        if count > MAX_ITEMS_PER_CATEGORY:
            notes.append(
                f"{category} 요구사항이 {count}건으로 비정상적으로 많습니다. "
                "프롬프트나 회의록 길이를 확인하세요."
            )
 
    return notes
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

DECISION_CATEGORY_BY_REQUIREMENT = {
    "non_functional": "non_functional",
    "data": "data",
    "technical": "tech",
}

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
    unresolved 모순 검사 — 모순된 안내 문구를 제거합니다.
 
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


def repair_feature_decision_categories(data: dict) -> list[str]:
    """
    feature로 잘못 분류된 품질·데이터·기술 결정을 보정합니다.

    의미를 추측해 분류하지 않습니다. evidence 검증이 끝난 뒤,
    verified 결정과 verified 요구사항이 정확히 같은 원문 quote를 사용하고
    그 quote가 functional에는 없으며 다른 요구사항 분류 하나에만 있을 때만
    해당 요구사항 분류로 옮깁니다.

    같은 quote가 여러 요구사항 분류에 걸치면 안전하게 기존 값을 유지합니다.
    scope 결정은 기능 요구사항과 같은 quote를 쓸 수 있으므로 수정하지 않습니다.
    """
    requirements = data.get("requirements") or {}
    quote_categories: dict[str, set[str]] = {}

    for category in REQ_CATEGORIES:
        for item in requirements.get(category, []) or []:
            if not isinstance(item, dict):
                continue

            if item.get("evidence_status") != "verified":
                continue

            evidence = item.get("evidence") or {}
            quote = (
                evidence.get("quote", "")
                if isinstance(evidence, dict)
                else ""
            )
            quote_key = normalize(str(quote))

            if quote_key:
                quote_categories.setdefault(
                    quote_key,
                    set(),
                ).add(category)

    notes: list[str] = []

    for decision in data.get("decisions", []) or []:
        if not isinstance(decision, dict):
            continue

        if decision.get("category") != "feature":
            continue

        if decision.get("evidence_status") != "verified":
            continue

        evidence = decision.get("evidence") or {}
        quote = (
            evidence.get("quote", "")
            if isinstance(evidence, dict)
            else ""
        )
        quote_key = normalize(str(quote))
        matched_categories = quote_categories.get(
            quote_key,
            set(),
        )

        # functional에도 같은 quote가 있으면 실제 기능 결정일 수 있으므로
        # 자동 보정하지 않습니다.
        if "functional" in matched_categories:
            continue

        candidates = {
            DECISION_CATEGORY_BY_REQUIREMENT[category]
            for category in matched_categories
            if category in DECISION_CATEGORY_BY_REQUIREMENT
        }

        if len(candidates) != 1:
            continue

        corrected_category = next(iter(candidates))
        decision["category"] = corrected_category
        notes.append(
            "결정사항 분류를 근거가 같은 요구사항 분류에 맞춰 "
            f"feature에서 {corrected_category}(으)로 보정했습니다: "
            f"{str(decision.get('content', ''))[:35]}"
        )

    return notes
 
 
def dedupe_requirement_categories(data: dict) -> list[str]:
    """
    같은 내용이 여러 요구사항 분류에 중복 등록된 항목을 제거합니다.

    ## 왜 필요한가

    실행 결과에서 같은 내용이 functional과 technical에 동일하게
    중복 등록되는 사례가 확인됐습니다
    (예: "주클로 모델을 사용하여 패션 데이터를 분류한다"가 두 분류
    모두에 들어감). 기획서 5·6·7번 섹션(주요 기능·기술 및 제약사항·
    최종 결정사항)이 이 requirements를 그대로 재료로 쓰므로, 중복을
    남겨두면 같은 내용이 서로 다른 섹션에 반복 표시됩니다.

    ## 왜 기록만 하지 않고 제거까지 하는가

    다른 교차 규칙은 대부분 판단이 필요해 기록만 하지만, 이 중복은
    원인이 한 가지뿐입니다 — 같은 content가 두 분류에 걸쳐 있으면
    같은 사실이 기능이면서 동시에 기술 스택일 수는 없으므로 하나는
    반드시 잘못된 분류입니다. 판단 없이 기계적으로 정리할 수 있는
    경우라 안전하게 제거합니다. check_unresolved_consistency와 같은
    이유로 제거하되, 제거 사실은 notes에 남겨 추적할 수 있게 합니다.

    REQ_CATEGORIES 순서(functional 우선)로 먼저 나온 분류를 남깁니다.
    같은 분류 안의 중복(예: non_functional 안에서 같은 내용이 두 번)은
    이 함수가 보는 대상이 아닙니다 — 분류 간 혼선만 봅니다.
    """
    reqs = data.get("requirements") or {}
    seen: dict[str, str] = {}
    notes: list[str] = []

    for category in REQ_CATEGORIES:
        items = reqs.get(category) or []
        kept: list = []

        for item in items:
            key = normalize(item.get("content", ""))

            # 다른 분류에 이미 등록된 내용만 중복으로 봅니다.
            # 같은 분류 안의 중복은 이 규칙의 대상이 아닙니다
            # (test_같은_분류_안의_중복은_기록하지_않는다 참고).
            if key and key in seen and seen[key] != category:
                notes.append(
                    f"중복 등록을 제거했습니다: {seen[key]}에 이미 있는 내용이 "
                    f"{category}에도 등록되어 있었습니다 — "
                    f"{str(item.get('content', ''))[:25]}"
                )
                continue

            if key and key not in seen:
                seen[key] = category

            kept.append(item)

        reqs[category] = kept

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

    # ── 결정사항 분류 보정 (검증된 동일 quote일 때만 수정) ────
    notes += repair_feature_decision_categories(data)

    # ── 요구사항 분류 간 중복 제거 (데이터 수정 있음) ─────────
    notes += dedupe_requirement_categories(data)

    # 규칙 1: 기술 결정이 있는데 기술 요구사항이 비어 있는가
    tech_decisions = [
        d for d in data.get("decisions", []) if d.get("category") == "tech"
    ]
    if tech_decisions and not reqs.get("technical"):
        notes.append(
            "기술 관련 결정사항이 있으나 기술 요구사항이 비어 있습니다. 확인이 필요합니다."
        )

    # 규칙 4: 항목 수가 비정상적으로 많은가 (프롬프트 폭주 신호)
    for category in REQ_CATEGORIES:
        count = len(reqs.get(category, []))
        if count > MAX_ITEMS_PER_CATEGORY:
            notes.append(
                f"{category} 요구사항이 {count}건으로 비정상적으로 많습니다. "
                "프롬프트나 회의록 길이를 확인하세요."
            )
 
    return notes

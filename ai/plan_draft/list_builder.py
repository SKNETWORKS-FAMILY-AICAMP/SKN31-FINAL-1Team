"""
목록형 섹션(3, 6, 7번) 조립.

LLM을 부르지 않습니다. 구조화 JSON의 배열을 HTML 목록으로 옮기는 일이라
코드가 하는 게 맞습니다.

## 왜 LLM을 안 쓰는가

LLM에 맡기면 문장을 다듬는 과정에서 원본에 없는 표현이 섞이고,
재생성할 때마다 순서나 표현이 달라집니다.
PM이 "아까 있던 항목이 왜 없지?"를 겪게 됩니다.

코드 조립은 원본 = 출력을 보장하고, 몇 번 돌려도 결과가 같습니다.

## items 필드

같은 내용을 두 형태로 담습니다.
  content_html : 화면에 그릴 용도 (<ul><li>...)
  items        : 하류 노드(③)가 쓸 용도 (태그 없는 배열)

노드 ③이 요구사항을 만들 때 HTML을 파싱하지 않아도 되게 하려는 것입니다.
어차피 배열을 갖고 있다가 HTML로 조립하므로 추가 비용이 거의 없습니다.
"""

from html import escape

# 근거 대조는 노드 1의 검증기와 같은 정규화를 써야 합니다.
# 기준이 갈리면 verified 근거가 노드 2에서 탈락합니다(_evidence_key 참고).
from meeting_analysis.validators.evidence import VERIFIED
from meeting_analysis.validators.evidence import normalize as _verifier_normalize

from .schemas import (
    Feature,
    PlanSection,
    SectionType,
    TechScopeGroup,
    VerifiedEvidence,
)


def _ul(lines: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{escape(t)}</li>" for t in lines) + "</ul>"


def _norm(text: str) -> str:
    """중복 판정용 정규화. 공백만 제거해 표현 차이를 흡수합니다."""
    return "".join(text.split())


def _evidence_key(text: str) -> str:
    """
    근거 대조용 정규화. 노드 1의 검증기와 같은 기준을 씁니다.

    ## 왜 _norm을 쓰면 안 되는가

    노드 1은 evidence.quote를 회의록과 대조할 때 공백과 문장부호를
    모두 제거합니다(validators/evidence.normalize). 반면 _norm은
    공백만 제거합니다.

    기준이 다르면 노드 1이 verified로 통과시킨 근거를 노드 2가
    탈락시킵니다. 노드 2가 인용을 옮겨 적으며 마침표 하나만 바꿔도
    항목 전체가 기획서에서 사라지는데, 작성자는 이유를 알 수 없습니다.

    근거 대조는 반드시 검증기와 같은 함수를 써야 하므로 여기서
    직접 가져옵니다. 중복 판정(_norm)과는 목적이 다른 별개 함수입니다.
    """
    return _verifier_normalize(str(text))


def _item_status(item: dict) -> str:
    """구조화 항목의 근거 검증 상태를 반환합니다."""
    evidence = item.get("evidence")

    if hasattr(evidence, "model_dump"):
        evidence = evidence.model_dump()

    evidence_status = (
        evidence.get("status")
        if isinstance(evidence, dict)
        else None
    )

    return str(
        item.get("evidence_status")
        or evidence_status
        or "unverified"
    ).strip()


def _verified_items(items: list) -> list[dict]:
    """verified 근거를 가진 딕셔너리 항목만 순서대로 반환합니다."""
    return [
        item
        for item in items
        if (
            isinstance(item, dict)
            and _item_status(item) == "verified"
        )
    ]


# 2026-09-16: 6·7번(기술 스택·최종 결정사항)은 예전엔 unverified 항목을
# _verified_items로 걸러 통째로 지웠습니다. 실측(실제 회의록 재실행)에서
# 노드 1이 내용은 맞게 뽑았는데 인용문을 옮겨 적다 한 글자 틀려서
# (예: "깔끔하게"→"깔끗하게") unverified가 된 결정사항이 화면에서
# 조용히 사라지는 사례를 확인했습니다. PM은 그런 결정이 논의됐는지조차
# 알 방법이 없었습니다.
#
# 이제 6·7번도 3번(세부 목표)처럼 unverified 항목을 지우지 않고
# 표시만 남깁니다 — 내용은 보여주되 "근거 확인 필요" 딱지를 붙여 PM이
# 원문을 대조해야 한다는 걸 알 수 있게 합니다. 틀린 걸 숨기는 것보다
# 확인이 필요하다고 티 내는 편이 낫습니다.
UNVERIFIED_ITEM_SUFFIX = " (근거 확인 필요)"

UNVERIFIED_ITEMS_NOTE = (
    "'(근거 확인 필요)' 표시가 붙은 항목은 회의록 원문과 근거 문장이 "
    "정확히 일치하지 않아 자동으로 확인되지 않았습니다. 내용 자체는 "
    "노드①이 뽑아낸 것이니, 원문과 직접 대조해 확정해 주세요."
)


def _mark_if_unverified(text: str, item: dict) -> tuple[str, bool]:
    """미확인 항목이면 표시를 붙입니다. (문장, 미확인 여부)를 반환합니다."""
    if _item_status(item) == VERIFIED:
        return text, False
    return text + UNVERIFIED_ITEM_SUFFIX, True


def _evidence_quote(item: dict) -> str:
    """구조화 항목에서 원문 근거 문자열을 가져옵니다."""
    evidence = item.get("evidence")

    if hasattr(evidence, "model_dump"):
        evidence = evidence.model_dump()

    if isinstance(evidence, dict):
        return str(
            evidence.get("quote", "")
        ).strip()

    return str(
        getattr(evidence, "quote", "")
        if evidence
        else ""
    ).strip()


def _as_sentence(text: str) -> str:
    """문장부호를 보존하면서 일반 텍스트를 한 문장으로 만듭니다."""
    text = str(text).strip()

    if not text:
        return ""

    if text.endswith((".", "!", "?")):
        return text

    return f"{text}."


def _is_feature_label_sentence(
    feature_name: str,
    content: str,
) -> bool:
    """
    기능명만 반복하는 상위 목록 문장인지 확인합니다.

    세부 조건이 존재할 때 이 문장을 함께 붙이면
    '기능을 제공한다. 세부 기능을 제공한다.'처럼 보이므로 생략합니다.
    기능명만 있는 경우에는 그대로 보존합니다.
    """
    normalized = _norm(content).rstrip(".!?")
    feature = _norm(feature_name)

    return normalized in {
        f"{feature}기능을제공한다",
        f"{feature}을제공한다",
        f"{feature}를제공한다",
        f"{feature}기능을포함한다",
    }

def _dedupe_evidence(
    evidence_items: list[VerifiedEvidence],
) -> list[VerifiedEvidence]:
    """
    같은 원문 근거가 한 섹션에 여러 번 표시되지 않도록 제거합니다.

    공백이나 줄바꿈만 다른 문장도 같은 근거로 판단합니다.
    처음 나온 근거의 순서는 유지합니다.
    """
    result: list[VerifiedEvidence] = []
    seen_quotes: set[str] = set()

    for evidence in evidence_items:
        quote = str(evidence.quote).strip()
        normalized_quote = _norm(quote)

        if not normalized_quote:
            continue

        if normalized_quote in seen_quotes:
            continue

        seen_quotes.add(normalized_quote)
        result.append(evidence)

    return result


def _ev(items: list[dict]) -> list[VerifiedEvidence]:
    """
    항목 dict들에서 evidence를 뽑습니다.

    evidence_status는 verify_and_mark()가 item에 직접 붙인 값(evidence와
    나란히 있는 형제 키)입니다. 예전엔 quote만 가져가고 이 값을 버렸는데,
    그러면 verified/unverified 구분이 사라져서 화면에서 근거를 신뢰할 수
    있는지 알 수 없었습니다. 지금은 status까지 같이 옮깁니다.
    """
    out: list[VerifiedEvidence] = []
    for i in items:
        e = i.get("evidence")
        quote = e.get("quote", "") if isinstance(e, dict) else getattr(e, "quote", "")
        if not quote:
            continue
        status = _item_status(i)
        out.append(VerifiedEvidence(quote=quote, status=status))
    return out


def collect_source_evidence(
    structured: dict,
    source_fields: list[str],
) -> list[VerifiedEvidence]:
    """
    SECTION_SPEC의 source_fields 경로를 따라가며
    노드 1에서 검증한 원문 근거를 수집합니다.

    동일한 근거는 한 섹션에서 한 번만 반환합니다.
    """
    out: list[VerifiedEvidence] = []
    seen_quotes: set[str] = set()

    def add(
        item: dict,
        evidence_key: str = "evidence",
        status_key: str = "evidence_status",
    ) -> None:
        """구조화 항목 하나에서 근거를 가져옵니다."""
        if not isinstance(item, dict):
            return

        evidence = item.get(evidence_key)

        if hasattr(evidence, "model_dump"):
            evidence = evidence.model_dump()

        if isinstance(evidence, dict):
            quote = evidence.get("quote", "")
        else:
            quote = (
                getattr(evidence, "quote", "")
                if evidence
                else ""
            )

        quote = str(quote).strip()
        quote_key = _norm(quote)

        if not quote_key:
            return

        if quote_key in seen_quotes:
            return

        seen_quotes.add(quote_key)

        if isinstance(evidence, dict):
            evidence_status = evidence.get("status")
        else:
            evidence_status = None

        status = str(
            item.get(status_key)
            or evidence_status
            or "unverified"
        ).strip()

        out.append(
            VerifiedEvidence(
                quote=quote,
                status=status,
            )
        )

    for field in source_fields:
        # decisions[feature] 같은 필터 경로
        if "[" in field:
            base, category = field.split("[", 1)
            category = category.rstrip("]")

            for item in structured.get(base, []):
                if not isinstance(item, dict):
                    continue

                if item.get("category") == category:
                    add(item)

            continue

        if field.startswith("project."):
            sub_field = field.split(".", 1)[1]
            project = structured.get("project") or {}

            # 전체 문제 근거
            if sub_field == "problem":
                add(
                    project,
                    evidence_key="problem_evidence",
                    status_key="problem_evidence_status",
                )
                continue

            # 개별 문제 근거
            if sub_field == "problem_items":
                for problem_item in (
                    project.get("problem_items")
                    or []
                ):
                    add(problem_item)

                continue

            # 프로젝트 목표 근거
            if sub_field == "goals":
                for goal in (
                    project.get("goals")
                    or []
                ):
                    add(goal)

                continue

            # 프로젝트명과 배경은 배경 근거 사용
            if sub_field in {
                "name",
                "background",
            }:
                add(
                    project,
                    evidence_key="background_evidence",
                    status_key="background_evidence_status",
                )
                continue

        # requirements.functional 같은 일반 점 경로
        current = structured

        for part in field.split("."):
            if not isinstance(current, dict):
                current = None
                break

            current = current.get(part)

            if current is None:
                break

        if isinstance(current, list):
            for item in current:
                add(item)

        elif isinstance(current, dict):
            add(current)

    return _dedupe_evidence(out)

def collect_feature_evidence(
    structured: dict,
) -> list[VerifiedEvidence]:
    """
    5번 주요 기능에 표시할 근거를 수집합니다.

    기능 요구사항과 기능 결정사항에는 같은 기능이 표현만 다르게
    중복 저장되는 경우가 많습니다.

    예:
    - 기능 요구사항: 알림을 제공하도록 개발합니다.
    - 기능 결정사항: 알림을 제공하기로 했습니다.

    두 근거를 모두 표시하면 같은 의미의 문장이 반복되므로
    requirements.functional의 근거를 우선 사용합니다.

    기능 요구사항이 하나도 없을 때만 decisions[feature]의 근거를
    예비 근거로 사용합니다.

    7번 최종 결정사항에서는 기존대로 decisions의 근거를 사용하므로
    결정 이력이 사라지는 것은 아닙니다.
    """
    requirements = structured.get("requirements") or {}
    functional = (
        requirements.get("functional")
        if isinstance(requirements, dict)
        else []
    ) or []
    verified_functional = _verified_items(functional)

    if verified_functional:
        return _dedupe_evidence(
            _ev(verified_functional)
        )

    verified_feature_decisions = _verified_items(
        [
            decision
            for decision in (
                structured.get("decisions")
                or []
            )
            if (
                isinstance(decision, dict)
                and decision.get("category") == "feature"
            )
        ]
    )

    return _dedupe_evidence(
        _ev(verified_feature_decisions)
    )


def decide_feature_groups(
    quote_groups: dict[str, set[str]],
) -> dict[str, str]:
    """
    기능마다 group을 판정합니다. LLM을 쓰지 않습니다.

    회의에서 "제공 기능은 A, B, C로 확정한다"처럼 여러 기능을 한 문장에
    열거하면, 그 문장 하나가 여러 feature_name의 공통 근거가 됩니다.
    quote_groups에 이미 그 관계가 들어 있습니다.

      공통 근거(두 개 이상의 기능이 같은 quote를 씀)에 포함된 기능
        -> 확정 기능 목록이므로 mvp

      자기 근거만 가진 기능
        -> 목록과 별개로 확정된 것이므로 integration

    ※ 열거 문장이 아예 없으면(공통 근거 0건) 판정 근거가 없습니다.
      이때 전부 integration으로 두면 확정 기능이 전멸하므로
      기본값인 mvp를 그대로 씁니다.
    """
    all_names = {
        name
        for names in quote_groups.values()
        for name in names
    }

    shared_names: set[str] = set()

    for names in quote_groups.values():
        if len(names) >= 2:
            shared_names |= names

    if not shared_names:
        return {name: "mvp" for name in all_names}

    return {
        name: ("mvp" if name in shared_names else "integration")
        for name in all_names
    }


def build_features(
    structured: dict,
) -> list[Feature]:
    """
    검증된 기능 요구사항을 feature_name 기준으로 조립합니다.

    같은 원문 quote가 정확히 하나의 기능 그룹과 결정사항을 연결하면,
    더 완전한 결정 문장을 기능 설명에 사용합니다. 여러 기능이 나열된
    공통 quote는 특정 기능에 임의로 붙이지 않습니다.

    이를 통해 기능명과 세부 조건을 보존하면서도 '기능을 제공한다'라는
    상위 문장과 상세 문장이 반복되는 결과를 줄입니다.
    """
    if not isinstance(structured, dict):
        raise TypeError(
            "structured는 딕셔너리여야 합니다."
        )

    requirements = (
        structured.get("requirements")
        or {}
    )

    functional = (
        requirements.get("functional")
        if isinstance(requirements, dict)
        else []
    ) or []

    grouped_items: dict[str, list[dict]] = {}
    seen_contents: dict[str, set[str]] = {}
    quote_groups: dict[str, set[str]] = {}
    ungrouped_items: list[dict] = []
    seen_ungrouped: set[str] = set()

    for item in _verified_items(functional):

        feature_name = item.get("feature_name")
        content = item.get("content")

        if not isinstance(content, str):
            continue

        content = content.strip()

        if not content:
            continue

        normalized_content = _norm(content)

        if not normalized_content:
            continue

        if not isinstance(feature_name, str):
            feature_name = ""
        else:
            feature_name = feature_name.strip()

        # 비어 있거나 Feature.title의 최대 길이를 넘는 이름은
        # 임의로 줄이지 않고 미분류 묶음으로 보존합니다.
        if not feature_name or len(feature_name) > 40:
            if normalized_content not in seen_ungrouped:
                seen_ungrouped.add(normalized_content)
                ungrouped_items.append(item)
            continue

        if feature_name not in grouped_items:
            grouped_items[feature_name] = []
            seen_contents[feature_name] = set()

        if normalized_content in seen_contents[feature_name]:
            continue

        seen_contents[feature_name].add(
            normalized_content
        )
        grouped_items[feature_name].append(item)

        quote_key = _norm(
            _evidence_quote(item)
        )

        if quote_key:
            quote_groups.setdefault(
                quote_key,
                set(),
            ).add(feature_name)

    # 하나의 기능 그룹과만 연결되는 동일 quote의 결정사항을 수집합니다.
    # MVP 기능 6개가 한 문장에 열거된 공통 근거처럼 여러 기능에 걸친
    # quote는 제외하므로 잘못된 기능 관계를 만들지 않습니다.
    decision_details: dict[str, list[dict]] = {}
    seen_decisions: dict[str, set[str]] = {}

    for decision in _verified_items(
        structured.get("decisions") or []
    ):
        quote_key = _norm(
            _evidence_quote(decision)
        )
        related_groups = quote_groups.get(
            quote_key,
            set(),
        )

        if len(related_groups) != 1:
            continue

        feature_name = next(iter(related_groups))
        content = str(
            decision.get("content", "")
        ).strip()
        content_key = _norm(content)

        if not content_key:
            continue

        feature_seen = seen_decisions.setdefault(
            feature_name,
            set(),
        )

        if content_key in feature_seen:
            continue

        feature_seen.add(content_key)
        decision_details.setdefault(
            feature_name,
            [],
        ).append(decision)

    features: list[Feature] = []

    feature_groups = decide_feature_groups(quote_groups)

    for feature_name, items in grouped_items.items():
        decisions = decision_details.get(
            feature_name,
            [],
        )
        decision_quote_keys = {
            _norm(_evidence_quote(decision))
            for decision in decisions
        }

        description_parts: list[str] = []
        seen_parts: set[str] = set()

        def add_part(text: str) -> None:
            sentence = _as_sentence(text)
            key = _norm(sentence)

            if not key or key in seen_parts:
                return

            seen_parts.add(key)
            description_parts.append(sentence)

        # 확정 결정은 논의 결과를 가장 완전하게 정리한 문장이므로 우선합니다.
        for decision in decisions:
            add_part(decision.get("content", ""))

        detailed_items = [
            item
            for item in items
            if not _is_feature_label_sentence(
                feature_name,
                str(item.get("content", "")),
            )
        ]

        for item in items:
            quote_key = _norm(
                _evidence_quote(item)
            )

            # 같은 quote의 더 완전한 결정 문장을 이미 사용했습니다.
            if quote_key in decision_quote_keys:
                continue

            # 세부 설명이 있으면 기능명만 되풀이하는 문장은 생략합니다.
            if (
                detailed_items
                and _is_feature_label_sentence(
                    feature_name,
                    str(item.get("content", "")),
                )
            ):
                continue

            add_part(item.get("content", ""))

        if not description_parts:
            for item in items:
                add_part(item.get("content", ""))

        # 2026-09-13: 설명이 기능명 반복뿐일 때 "세부 내용은 논의되지
        # 않았습니다"로 바꿔봤다가 되돌렸습니다. 실행해 보니 MVP 기능
        # 6개가 전부 그 문장이 되어, 같은 줄이 6번 반복됐습니다.
        # 담긴 정보는 이전과 같은데 기획서는 텅 빈 것처럼 보였습니다.
        #
        # 기능명만 논의된 경우를 표시하려면 기능마다 문장을 붙일 게
        # 아니라 그런 기능들을 한 번에 묶어 보여줘야 합니다.
        features.append(
            Feature(
                title=feature_name,
                description=" ".join(
                    description_parts
                ),
                group=feature_groups.get(
                    feature_name,
                    "mvp",
                ),
            )
        )

    if ungrouped_items:
        features.append(
            Feature(
                title="기타 기능 요구사항",
                description=" ".join(
                    _as_sentence(
                        item.get("content", "")
                    )
                    for item in ungrouped_items
                ),
            )
        )

    if features:
        return features

    feature_decisions = _verified_items(
        [
            decision
            for decision in (
                structured.get("decisions")
                or []
            )
            if (
                isinstance(decision, dict)
                and decision.get("category") == "feature"
            )
        ]
    )
    decision_contents: list[str] = []
    seen_decisions: set[str] = set()

    for decision in feature_decisions:
        content = decision.get("content")

        if not isinstance(content, str):
            continue

        content = content.strip()
        normalized_content = _norm(content)

        if (
            not normalized_content
            or normalized_content in seen_decisions
        ):
            continue

        seen_decisions.add(normalized_content)
        decision_contents.append(content)

    if decision_contents:
        return [
            Feature(
                title="확정 기능",
                description=" ".join(
                    _as_sentence(content)
                    for content in decision_contents
                ),
            )
        ]

    return []

def collect_core_goal_evidence(
    structured: dict,
) -> list[VerifiedEvidence]:
    """
    2번 핵심 목표에 표시할 근거를 선별합니다.

    노드 1에서 프로젝트 목표를 추출했다면 해당 목표의 근거만
    사용합니다. 배경과 개별 문제를 모두 표시하면 핵심 목표의
    근거가 지나치게 길어지기 때문입니다.

    프로젝트 목표가 없어서 노드 2가 핵심 목표를 보완한 경우에는
    개별 문제와 기능 요구사항의 근거를 사용합니다.

    화면에서 읽기 어려울 정도로 근거가 많아지는 것을 방지하기
    위해 최대 4개까지만 반환합니다.
    """
    goal_evidence = collect_source_evidence(
        structured,
        ["project.goals"],
    )

    if goal_evidence:
        return _dedupe_evidence(goal_evidence)[:4]

    fallback_evidence = collect_source_evidence(
        structured,
        [
            "project.problem_items",
            "requirements.functional",
        ],
    )

    if fallback_evidence:
        return _dedupe_evidence(fallback_evidence)[:4]

    summary_evidence = collect_source_evidence(
        structured,
        [
            "project.problem",
            "project.background",
        ],
    )

    return _dedupe_evidence(summary_evidence)[:4]



GOALS_NOT_DISCUSSED_NOTE = (
    "회의에서 프로젝트 목표가 논의되지 않아 문제 정의만 정리했습니다. "
    "목표는 작성자가 직접 추가해야 합니다."
)


def _build_goals_problem_only(structured: dict, source_fields: list[str]) -> PlanSection:
    """
    3번 폴백 — LLM이 goals를 하나도 못 냈을 때 검증된 문제만 보여줍니다.

    project.problem_items에 검증된 문제가 있는데 LLM이 goals를 빈
    배열로 낸 경우(드묾, 모델 변동성) 섹션을 통째로 비우지 않고
    검증된 문제 목록만이라도 남깁니다. 목표는 지어내지 않습니다.
    """
    project = structured.get("project") or {}
    problems = [
        str(item.get("content", "")).strip()
        for item in _verified_items(project.get("problem_items") or [])
        if str(item.get("content", "")).strip()
    ]

    if not problems:
        return PlanSection(
            no=3,
            key="goals",
            title="세부 목표 및 문제 정의",
            section_type=SectionType.LIST,
            content_html="",
            items=[],
            source_fields=source_fields,
            is_incomplete=True,
        )

    content_html = (
        "<ul>"
        + "".join(
            f"<li><p><strong>문제:</strong> {escape(problem)}</p></li>"
            for problem in problems
        )
        + "</ul>"
        + f"<p>{escape(GOALS_NOT_DISCUSSED_NOTE)}</p>"
    )

    return PlanSection(
        no=3,
        key="goals",
        title="세부 목표 및 문제 정의",
        section_type=SectionType.LIST,
        content_html=content_html,
        items=[f"문제: {problem}" for problem in problems],
        source_fields=source_fields,
        evidence=collect_source_evidence(structured, ["project.problem_items"]),
        needs_input=GOALS_NOT_DISCUSSED_NOTE,
        is_incomplete=True,
    )


def build_goals(
    structured: dict,
    generated_goals: list | None = None,
) -> PlanSection:
    """
    3. 세부 목표 및 문제 정의

    2026-09-15: 문제-목표를 원문 quote 완전 일치로만 짝짓던 예전 방식을
    없앴습니다. 실측(같은 회의록, develop 브랜치와 비교) 결과 항목이
    1개만 남는 경우가 잦았습니다(345자 vs develop 1503자) — quote를
    LLM이 한 글자라도 다르게 쓰면 탈락했기 때문입니다.

    이제 project.problem_items·project.goals를 LLM에게 통째로 주고
    문제-목표를 직접 정리하게 합니다(plan_draft/schemas.py
    PlanSections.goals, plan_generation.yaml detailed_goal_rules).
    title/problem/goal이 모두 채워진 항목을 그대로 받아들이고, 항목별
    근거 매칭은 하지 않습니다 — 화면에 보여줄 근거는 섹션 전체 단위로
    project.problem_items·project.goals의 검증된 원문을 붙입니다
    (6·7번과 같은 방식). LLM이 project.problem_items에 없는 문제를
    지어내는 것은 프롬프트 규칙이 막습니다.
    """
    source_fields = [
        "project.problem",
        "project.problem_items",
        "project.goals",
    ]

    items_out: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for generated_goal in generated_goals or []:
        if hasattr(generated_goal, "model_dump"):
            goal_data = generated_goal.model_dump()
        elif isinstance(generated_goal, dict):
            goal_data = generated_goal
        else:
            continue

        title = str(goal_data.get("title", "")).strip()
        problem = str(goal_data.get("problem", "")).strip()
        goal = str(goal_data.get("goal", "")).strip()

        # 제목, 문제, 목표 중 하나라도 비어 있으면 완전한 항목이 아니므로 제외합니다.
        if not title or not problem or not goal:
            continue

        key = (_norm(problem), _norm(goal))

        if key in seen:
            continue

        seen.add(key)
        items_out.append({"title": title, "problem": problem, "goal": goal})

    # LLM이 항목을 하나도 못 냈으면(모델 변동성) 검증된 문제만이라도 보여줍니다.
    if not items_out:
        return _build_goals_problem_only(structured, source_fields)

    html_items = [
        "".join(
            [
                "<li>",
                f"<strong>{escape(item['title'])}</strong>",
                "<p>",
                "<strong>문제:</strong> ",
                f"{escape(item['problem'])}",
                "</p>",
                "<p>",
                "<strong>목표:</strong> ",
                f"{escape(item['goal'])}",
                "</p>",
                "</li>",
            ]
        )
        for item in items_out
    ]

    content_html = "<ul>" + "".join(html_items) + "</ul>"

    items = [
        "\n".join(
            [
                item["title"],
                f"문제: {item['problem']}",
                f"목표: {item['goal']}",
            ]
        )
        for item in items_out
    ]

    # 항목별 매칭이 아니라 섹션 전체 근거를 붙입니다(6·7번과 같은 방식).
    evidence = collect_source_evidence(
        structured,
        ["project.problem_items", "project.goals"],
    )

    return PlanSection(
        no=3,
        key="goals",
        title="세부 목표 및 문제 정의",
        section_type=SectionType.LIST,
        content_html=content_html,
        items=items,
        source_fields=source_fields,
        evidence=evidence,
        is_incomplete=False,
    )

def build_tech_scope(structured: dict) -> PlanSection:
    """
    6. 기술 및 제약사항

    소제목 4개로 구성합니다. 회의에서 안 나온 소제목은 아예 표시되지 않으므로
    대부분의 회의록에서는 기술 스택과 제약사항 두 개만 보입니다.

        기술 스택       requirements.technical + decisions[tech]
        비기능 요구사항 requirements.non_functional
        데이터 요구     requirements.data
        일정·인력 제약   constraints

    decisions[scope]는 7번 최종 결정사항에서 표시합니다.
    같은 범위 결정을 6번과 7번에 반복하지 않습니다.
    """
    reqs = structured.get("requirements", {})

    parts: list[str] = []
    items: list[str] = []
    groups: list[TechScopeGroup] = []
    evidence: list[VerifiedEvidence] = []

    # 한 섹션 안에서 같은 문장이 두 번 나오지 않게 추적합니다.
    #
    # 구조화 단계에서 같은 내용이 여러 분류에 들어가는 경우가 있습니다.
    # 예를 들어 "POS 연동은 A사만 유지한다"가 requirements.technical과
    # decisions[scope]에 모두 잡히면, 기술 스택과 제약사항에 같은 문장이
    # 두 번 나와 PM 눈에 이상하게 보입니다.
    #
    # 먼저 나온 소제목에 남기고 이후 소제목에서는 건너뜁니다.
    # (섹션 간 중복은 건드리지 않습니다. 6번과 7번은 관점이 달라
    #  같은 결정이 양쪽에 나오는 것이 의도된 동작입니다.)
    seen_lines: set[str] = set()
    has_unverified = False

    def add(title: str, sources: list[dict], render) -> None:
        """
        항목을 조립하고 이미 나온 문장은 제외합니다.

        unverified 항목도 지우지 않고 포함하되 표시를 붙입니다
        (UNVERIFIED_ITEM_SUFFIX 참고) — 이유는 이 파일의 해당 상수
        정의부 주석을 보세요.
        """
        nonlocal has_unverified
        lines, used = [], []
        for s in sources:
            if not isinstance(s, dict):
                continue
            text = render(s)
            key = _norm(text)
            if not key or key in seen_lines:
                continue
            seen_lines.add(key)
            text, unverified = _mark_if_unverified(text, s)
            has_unverified = has_unverified or unverified
            lines.append(text)
            used.append(s)

        if not lines:
            return
        parts.append(f"<p><strong>{title}</strong></p>" + _ul(lines))
        items.extend(lines)
        groups.append(TechScopeGroup(subtitle=title, items=lines))
        evidence.extend(_ev(used))

    # ── 기술 스택 ────────────────────────────────────────────
    # requirements.technical + decisions[tech]
    #
    # ## 두 번에 걸친 변경 이력
    #
    # 원래는 requirements.technical만 썼습니다. 그러면 바코드 구현 방식처럼
    # 결정으로만 잡히는 기술이 6번에서 통째로 빠집니다.
    #
    # 1차 시도(실패): decisions[tech]를 그냥 넣었습니다. 당시 노드 1은
    # 바코드 구현 방식을 tech가 아니라 feature로 분류하고 있어서,
    # tech 결정은 기술 스택 선언 1건뿐이었습니다. requirements.technical과
    # 같은 내용이라 중복 한 줄만 늘고 얻는 건 없어 되돌렸습니다.
    #
    # 2차(현재): 노드 1의 분류 규칙을 고쳐 "이미 제공하기로 한 기능을
    # 무엇으로 구현할지"는 tech로 가게 했습니다. 이제 바코드 구현 방식이
    # tech 결정으로 잡히므로 다시 넣습니다.
    #
    # ## 중복을 두 단계로 막습니다
    #
    # seen_lines는 문장이 같을 때만 걸러냅니다. 그런데 같은 사실이
    # 요구사항과 결정에 표현만 다르게 들어가는 일이 흔합니다
    # ("... AWS를 사용한다" / "기술 스택은 ... 로 확정하고"). 그래서
    # 이미 쓴 항목과 같은 원문을 근거로 삼은 결정은 건너뜁니다.
    # 노드 1이 같은 quote를 쓴다면 같은 논의를 가리키는 것이기 때문입니다.
    #
    # 7번과 겹치는 건 의도된 동작입니다. 6번은 rationale 없이
    # "무엇을 쓰는가"만, 7번은 이유까지 붙여 "왜 정했는가"를 보여줍니다.
    technical_items = list(reqs.get("technical", []) or [])

    # verified 여부와 무관하게 전부 봅니다 — 이제 unverified 항목도
    # add()가 지우지 않고 표시만 붙여 포함하므로, 같은 quote를 쓴 tech
    # 결정을 걸러내는 기준도 verified로 한정할 이유가 없습니다.
    used_quotes = {
        _evidence_key(_evidence_quote(item))
        for item in technical_items
        if isinstance(item, dict)
    }
    used_quotes.discard("")

    tech_decisions = [
        decision
        for decision in (structured.get("decisions") or [])
        if (
            isinstance(decision, dict)
            and decision.get("category") == "tech"
            and _evidence_key(_evidence_quote(decision)) not in used_quotes
        )
    ]

    add(
        "기술 스택",
        technical_items + tech_decisions,
        lambda s: s["content"],
    )

    # ── 비기능 요구사항 ──────────────────────────────────────
    add("비기능 요구사항", reqs.get("non_functional", []), lambda s: s["content"])

    # ── 데이터 요구 ──────────────────────────────────────────
    add("데이터 요구", reqs.get("data", []), lambda s: s["content"])

    # ── 제약사항 ─────────────────────────────────────────────
    # 범위 결정은 7번에만 두고, 여기에는 실제 일정·인력 등의 제약만 둡니다.
    constraints: list[dict] = list(
        structured.get("constraints", [])
    )
    add(
        "일정·인력 제약", constraints,
        lambda s: f"[{s['type']}] {s['content']}" if s.get("type") else s["content"],
    )

    return PlanSection(
        no=6, key="tech_scope", title="기술 스택 및 제약사항",
        section_type=SectionType.LIST,
        content_html="".join(parts),
        items=items,
        groups=groups,
        source_fields=[
            "requirements.technical", "requirements.non_functional",
            "requirements.data", "decisions[tech]",
            "constraints",
        ],
        evidence=_dedupe_evidence(evidence),
        is_incomplete=not parts,
        needs_input=UNVERIFIED_ITEMS_NOTE if has_unverified else "",
    )


def build_decisions(structured: dict) -> PlanSection:
    """
    7. 최종 결정사항

    decisions 전체를 의사결정 이력으로 기록합니다.
    6번과 항목이 겹치지만 관점이 다릅니다.
    6번은 "무엇을 쓰고 무엇이 제약인가", 7번은 "무엇을 왜 결정했는가"입니다.

    ※ 노드 ③ 주의: decisions의 feature·tech 항목은 requirements와
      내용이 겹칩니다. 고유한 것은 scope뿐이므로 한쪽만 사용하세요.

    2026-09-16: verified만 남기던 필터를 없앴습니다. unverified라고
    항목을 지우면, 내용은 맞게 뽑혔는데 인용문 한 글자 오차로 조용히
    사라지는 결정사항이 생깁니다(실측 확인 — UNVERIFIED_ITEM_SUFFIX
    정의부 주석 참고). 이제 전부 포함하되 unverified 항목에는 표시를
    붙입니다.
    """
    decisions = [
        d for d in (structured.get("decisions") or [])
        if isinstance(d, dict)
    ]

    if not decisions:
        return PlanSection(
            no=7, key="decisions", title="최종 결정사항",
            section_type=SectionType.LIST,
            content_html="", items=[],
            source_fields=["decisions"],
            is_incomplete=True,
        )

    label = {
        "feature": "기능",
        "non_functional": "비기능 요구사항",
        "data": "데이터",
        "tech": "기술",
        "scope": "범위",
    }
    lines = []
    has_unverified = False
    for d in decisions:
        text = f"[{label.get(d['category'], d['category'])}] {d['content']}"
        if d.get("rationale"):
            text += f" — {d['rationale']}"
        text, unverified = _mark_if_unverified(text, d)
        has_unverified = has_unverified or unverified
        lines.append(text)

    return PlanSection(
        no=7, key="decisions", title="최종 결정사항",
        section_type=SectionType.LIST,
        content_html=_ul(lines),
        items=lines,
        source_fields=["decisions"],
        evidence=_dedupe_evidence(_ev(decisions)),
        needs_input=UNVERIFIED_ITEMS_NOTE if has_unverified else "",
    )


def build_all(
    structured: dict,
    generated_goals: list | None = None,
) -> list[PlanSection]:
    """목록형 섹션을 조립합니다."""
    return [
        build_goals(structured, generated_goals),
        build_tech_scope(structured),
        build_decisions(structured),
    ]
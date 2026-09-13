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

        features.append(
            Feature(
                title=feature_name,
                description=" ".join(
                    description_parts
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



def build_goals(
    structured: dict,
    generated_goals: list | None = None,
) -> PlanSection:
    """
    3. 세부 목표 및 문제 정의

    노드 2가 생성한 DetailedGoal을 검증한 뒤 기획서 섹션으로 조립합니다.

    각 세부 목표에는 다음 항목이 필요합니다.

        title
        problem
        goal
        problem_evidence
        goal_evidence

    노드 1에 project.goals가 있더라도 그대로 목록으로 출력하지 않습니다.
    노드 2가 문제와 목표의 관계를 묶어 만든 결과를 사용합니다.

    단, 노드 2가 제출한 근거가 노드 1의 검증된 근거와 일치할 때만
    최종 기획서에 포함합니다.
    """
    from html import escape

    project = structured.get("project") or {}
    source_fields = [
        "project.problem",
        "project.problem_items",
        "project.goals",
    ]

    # 문제에 사용할 수 있는 검증된 근거입니다.
    #
    # project.problem_evidence와
    # project.problem_items[].evidence만 등록합니다.
    allowed_problem_evidence: dict[str, str] = {}

    # 목표에 사용할 수 있는 검증된 근거입니다.
    #
    # project.goals의 근거만 등록합니다.
    # 기능 요구사항을 목표 근거로 허용하면 문제와 기능 사이의
    # 인과관계를 LLM이 임의로 만들 수 있습니다.
    allowed_goal_evidence: dict[str, str] = {}

    def register_evidence(
        destination: dict[str, str],
        item: dict,
        evidence_key: str = "evidence",
        status_key: str = "evidence_status",
    ) -> None:
        """
        노드 1에서 verified로 판정된 근거만 허용 목록에 등록합니다.

        딕셔너리의 key에는 공백과 줄바꿈을 정규화한 문장을 저장하고,
        value에는 노드 1이 가진 원래 quote를 저장합니다.

        이렇게 하면 LLM이 줄바꿈을 공백으로 바꾼 경우에도 비교할 수 있지만,
        최종 기획서에는 노드 1의 원래 quote가 들어갑니다.
        """
        if not isinstance(item, dict):
            return

        evidence = item.get(evidence_key)

        if hasattr(evidence, "model_dump"):
            evidence = evidence.model_dump()

        if not isinstance(evidence, dict):
            return

        quote = str(
            evidence.get("quote", "")
        ).strip()

        status = str(
            item.get(status_key)
            or evidence.get("status")
            or "unverified"
        ).strip()

        normalized_quote = _norm(quote)

        if (
            not normalized_quote
            or status != "verified"
        ):
            return

        destination[normalized_quote] = quote

    # 전체 문제의 근거를 등록합니다.
    register_evidence(
        allowed_problem_evidence,
        project,
        evidence_key="problem_evidence",
        status_key="problem_evidence_status",
    )

    # 개별 문제의 근거를 등록합니다.
    for problem_item in (
        project.get("problem_items")
        or []
    ):
        register_evidence(
            allowed_problem_evidence,
            problem_item,
        )

    # 노드 1에서 추출한 목표 근거를 등록합니다.
    for project_goal in (
        project.get("goals")
        or []
    ):
        register_evidence(
            allowed_goal_evidence,
            project_goal,
        )

    def match_evidence(
        evidence_items: list,
        allowed_evidence: dict[str, str],
    ) -> list[VerifiedEvidence]:
        """
        노드 2가 제출한 근거가 검증된 허용 근거인지 확인합니다.

        허용되지 않은 근거는 제외합니다.
        같은 근거가 여러 번 전달되면 한 번만 사용합니다.
        """
        matched: list[VerifiedEvidence] = []
        seen_quotes: set[str] = set()

        for evidence in evidence_items:
            if hasattr(evidence, "model_dump"):
                evidence = evidence.model_dump()

            if not isinstance(evidence, dict):
                continue

            submitted_quote = str(
                evidence.get("quote", "")
            ).strip()

            normalized_quote = _norm(
                submitted_quote
            )

            # 노드 2가 작성한 quote가 노드 1의 verified 근거와
            # 일치하지 않으면 사용하지 않습니다.
            original_quote = allowed_evidence.get(
                normalized_quote
            )

            if not original_quote:
                continue

            if original_quote in seen_quotes:
                continue

            seen_quotes.add(original_quote)

            matched.append(
                VerifiedEvidence(
                    quote=original_quote,
                    status="verified",
                )
            )

        return matched

    accepted_goals: list[dict] = []
    items: list[str] = []
    section_evidence: list[VerifiedEvidence] = []

    seen_goal_pairs: set[tuple[str, str]] = set()
    seen_section_quotes: set[str] = set()

    for generated_goal in generated_goals or []:
        if hasattr(generated_goal, "model_dump"):
            goal_data = generated_goal.model_dump()
        elif isinstance(generated_goal, dict):
            goal_data = generated_goal
        else:
            continue

        title = str(
            goal_data.get("title", "")
        ).strip()

        problem = str(
            goal_data.get("problem", "")
        ).strip()

        goal = str(
            goal_data.get("goal", "")
        ).strip()

        # 제목, 문제, 목표 중 하나라도 비어 있으면
        # 완전한 세부 목표 항목이 아니므로 제외합니다.
        if not title or not problem or not goal:
            continue

        normalized_pair = (
            _norm(problem),
            _norm(goal),
        )

        # 같은 문제와 목표의 조합은 한 번만 사용합니다.
        if normalized_pair in seen_goal_pairs:
            continue

        problem_evidence = match_evidence(
            goal_data.get(
                "problem_evidence",
                [],
            ),
            allowed_problem_evidence,
        )

        goal_evidence = match_evidence(
            goal_data.get(
                "goal_evidence",
                [],
            ),
            allowed_goal_evidence,
        )

        # 문제 근거와 목표 근거가 모두 있어야 합니다.
        #
        # 한쪽 근거만 있으면 문제와 목표의 연결 관계를
        # 검증할 수 없으므로 해당 항목을 제외합니다.
        if (
            not problem_evidence
            or not goal_evidence
        ):
            continue

        seen_goal_pairs.add(normalized_pair)

        accepted_goals.append(
            {
                "title": title,
                "problem": problem,
                "goal": goal,
            }
        )

        # items에는 편집과 확인에 사용할 수 있는
        # 일반 텍스트 형태를 저장합니다.
        items.append(
            "\n".join(
                [
                    title,
                    f"문제: {problem}",
                    f"목표: {goal}",
                ]
            )
        )

        # 섹션 전체 근거에는 문제 근거와 목표 근거를 합칩니다.
        # 같은 quote는 한 번만 저장합니다.
        for evidence in (
            problem_evidence
            + goal_evidence
        ):
            if evidence.quote in seen_section_quotes:
                continue

            seen_section_quotes.add(
                evidence.quote
            )

            section_evidence.append(evidence)

        # 스키마와 프롬프트의 최대 개수는 4개입니다.
        if len(accepted_goals) >= 4:
            break

    # 화면 표시용 HTML을 만듭니다.
    #
    # 항목 번호는 넣지 않습니다.
    # ul과 li가 글머리 기호를 표시합니다.
    html_items: list[str] = []

    for item in accepted_goals:
        html_items.append(
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
        )

    content_html = (
        "<ul>"
        + "".join(html_items)
        + "</ul>"
        if html_items
        else ""
    )

    return PlanSection(
        no=3,
        key="goals",
        title="세부 목표 및 문제 정의",
        section_type=SectionType.LIST,
        content_html=content_html,
        items=items,
        source_fields=source_fields,
        evidence=_dedupe_evidence(section_evidence),
        is_incomplete=not accepted_goals,
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

    def add(title: str, sources: list[dict], render) -> None:
        """verified 항목을 조립하고 이미 나온 문장은 제외합니다."""
        lines, used = [], []
        for s in _verified_items(sources):
            text = render(s)
            key = _norm(text)
            if not key or key in seen_lines:
                continue
            seen_lines.add(key)
            lines.append(text)
            used.append(s)

        if not lines:
            return
        parts.append(f"<p><strong>{title}</strong></p>" + _ul(lines))
        items.extend(lines)
        groups.append(TechScopeGroup(subtitle=title, items=lines))
        evidence.extend(_ev(used))

    # ── 기술 스택 ────────────────────────────────────────────
    # requirements.technical만 사용합니다.
    # decisions[tech]는 넣지 않습니다 — 같은 내용이 표현만 달라 중복되고,
    # 어차피 7번 최종 결정사항에 전부 들어갑니다.
    add("기술 스택", reqs.get("technical", []), lambda s: s["content"])

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
    )


def build_decisions(structured: dict) -> PlanSection:
    """
    7. 최종 결정사항

    decisions 전체를 의사결정 이력으로 기록합니다.
    6번과 항목이 겹치지만 관점이 다릅니다.
    6번은 "무엇을 쓰고 무엇이 제약인가", 7번은 "무엇을 왜 결정했는가"입니다.

    ※ 노드 ③ 주의: decisions의 feature·tech 항목은 requirements와
      내용이 겹칩니다. 고유한 것은 scope뿐이므로 한쪽만 사용하세요.
    """
    decisions = _verified_items(
        structured.get("decisions", [])
        or []
    )

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
    for d in decisions:
        text = f"[{label.get(d['category'], d['category'])}] {d['content']}"
        if d.get("rationale"):
            text += f" — {d['rationale']}"
        lines.append(text)

    return PlanSection(
        no=7, key="decisions", title="최종 결정사항",
        section_type=SectionType.LIST,
        content_html=_ul(lines),
        items=lines,
        source_fields=["decisions"],
        evidence=_dedupe_evidence(_ev(decisions)),
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

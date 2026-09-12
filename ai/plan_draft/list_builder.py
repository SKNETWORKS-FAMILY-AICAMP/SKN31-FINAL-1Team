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

from .schemas import PlanSection, SectionType, TechScopeGroup, VerifiedEvidence


def _ul(lines: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{escape(t)}</li>" for t in lines) + "</ul>"


def _norm(text: str) -> str:
    """중복 판정용 정규화. 공백만 제거해 표현 차이를 흡수합니다."""
    return "".join(text.split())

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
        status = i.get("evidence_status", "unverified")
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
    functional_evidence = collect_source_evidence(
        structured,
        ["requirements.functional"],
    )

    if functional_evidence:
        return _dedupe_evidence(functional_evidence)

    decision_evidence = collect_source_evidence(
        structured,
        ["decisions[feature]"],
    )

    return _dedupe_evidence(decision_evidence)


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
    requirements = structured.get("requirements") or {}
    decisions = structured.get("decisions") or []

    source_fields = [
    "project.problem",
    "project.problem_items",
    "project.goals",
    "requirements.functional",
    "decisions[feature]",
    ]

    # 문제에 사용할 수 있는 검증된 근거입니다.
    #
    # project.problem_evidence와
    # project.problem_items[].evidence만 등록합니다.
    allowed_problem_evidence: dict[str, str] = {}

    # 목표에 사용할 수 있는 검증된 근거입니다.
    #
    # project.goals, requirements.functional,
    # feature 범주의 decisions 근거만 등록합니다.
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

    # 기능 요구사항의 근거를 목표 근거로 등록합니다.
    for requirement in (
        requirements.get("functional")
        or []
    ):
        register_evidence(
            allowed_goal_evidence,
            requirement,
        )

    # 기능 범주의 최종 결정만 목표 근거로 등록합니다.
    for decision in decisions:
        if not isinstance(decision, dict):
            continue

        if decision.get("category") != "feature":
            continue

        register_evidence(
            allowed_goal_evidence,
            decision,
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
        성능·보안 요구  requirements.non_functional
        데이터 요구     requirements.data
        제약사항        constraints + decisions[scope]
    """
    reqs = structured.get("requirements", {})
    decisions = structured.get("decisions", [])

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
        """소제목 하나를 조립합니다. 이미 나온 문장은 제외합니다."""
        lines, used = [], []
        for s in sources:
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

    # ── 성능·보안 요구 ───────────────────────────────────────
    add("성능·보안 요구", reqs.get("non_functional", []), lambda s: s["content"])

    # ── 데이터 요구 ──────────────────────────────────────────
    add("데이터 요구", reqs.get("data", []), lambda s: s["content"])

    # ── 제약사항 ─────────────────────────────────────────────
    # constraints는 type이 있고(일정/인력 등), scope 결정은 없습니다.
    scope: list[dict] = list(structured.get("constraints", []))
    scope += [d for d in decisions if d.get("category") == "scope"]
    add(
        "제약사항", scope,
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
            "constraints", "decisions[scope]",
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
    decisions = structured.get("decisions", [])

    if not decisions:
        return PlanSection(
            no=7, key="decisions", title="최종 결정사항",
            section_type=SectionType.LIST,
            content_html="", items=[],
            source_fields=["decisions"],
            is_incomplete=True,
        )

    label = {"feature": "기능", "tech": "기술", "scope": "범위"}
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
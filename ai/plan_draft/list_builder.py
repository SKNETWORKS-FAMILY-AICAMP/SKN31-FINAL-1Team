"""
나열형 섹션(6, 7번) 조립.

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


def collect_source_evidence(structured: dict, source_fields: list[str]) -> list[VerifiedEvidence]:
    """
    서술형 섹션(1~5번, 주요기능 포함)의 근거를 노드①이 이미 검증해둔
    원본 데이터에서 그대로 재수집합니다.

    왜 필요한가: NarrativeSection.evidence는 노드②의 LLM이 문장을 쓰면서
    스스로 인용한 것이라, 원문과 실제로 대조된 적이 없습니다(unverified가
    아니라 아예 검증 자체가 없음). 반면 requirements.functional, users,
    scenarios, decisions, project 같은 원본 항목들은 verify_and_mark()가
    이미 evidence_status를 붙여둔 상태입니다. LLM에게 근거를 다시 찾게
    시키는 대신(모델이 더 그럴듯한 인용을 지어냄 — evidence.py 주석 참조),
    agent.py가 SECTION_SPEC의 source_fields 경로를 그대로 따라가서 이
    검증된 근거를 가져다 씁니다.

    source_fields 예시와 처리 방식:
      "project.name" / "project.background"
          → background_evidence를 가져옵니다.
      "project.problem"
          → problem_evidence를 가져옵니다.
            (project는 background_evidence/problem_evidence로 근거가 나뉘어
            있습니다 — meeting_analysis/schemas.py Project 참고)
      "users" / "scenarios" / "requirements.functional"
          → 배열입니다. 각 항목의 evidence를 전부 모읍니다.
      "decisions[feature]"
          → decisions 중 category가 "feature"인 것만 모읍니다
            (_source_is_empty()와 같은 대괄호 표기 규칙).
    """
    out: list[VerifiedEvidence] = []
    seen_quotes: set[str] = set()

    def add(item: dict, evidence_key: str = "evidence", status_key: str = "evidence_status") -> None:
        if not isinstance(item, dict):
            return
        e = item.get(evidence_key)
        quote = e.get("quote", "") if isinstance(e, dict) else getattr(e, "quote", "") if e else ""
        if not quote or quote in seen_quotes:
            return
        seen_quotes.add(quote)
        status = item.get(status_key, "unverified")
        out.append(VerifiedEvidence(quote=quote, status=status))

    for field in source_fields:
        if "[" in field:                       # decisions[feature] 형태
            base, cat = field.split("[")
            cat = cat.rstrip("]")
            for d in structured.get(base, []):
                if isinstance(d, dict) and d.get("category") == cat:
                    add(d)
            continue

        if field.startswith("project."):
            # 2026-09-07: project.evidence가 background_evidence/problem_evidence로
            # 나뉘었습니다(schemas.py Project 참고). project.problem을 가리키면
            # problem_evidence를, 그 외(project.name, project.background)는
            # background_evidence를 가져옵니다 — name은 따로 근거가 없고
            # background와 함께 1번 개요 섹션에 쓰이기 때문입니다.
            sub = field.split(".", 1)[1]
            proj = structured.get("project") or {}
            if sub == "problem":
                add(proj, "problem_evidence", "problem_evidence_status")
            else:
                add(proj, "background_evidence", "background_evidence_status")
            continue

        # "requirements.functional" 같은 점 경로를 따라갑니다.
        cur = structured
        for part in field.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
            if cur is None:
                break

        if isinstance(cur, list):
            for item in cur:
                add(item)
        elif isinstance(cur, dict):
            add(cur)

    return out


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
        no=6, key="tech_scope", title="기술 및 제약사항",
        section_type=SectionType.LIST,
        content_html="".join(parts),
        items=items,
        groups=groups,
        source_fields=[
            "requirements.technical", "requirements.non_functional",
            "requirements.data", "decisions[tech]",
            "constraints", "decisions[scope]",
        ],
        evidence=evidence,
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
        evidence=_ev(decisions),
    )


def build_all(structured: dict) -> list[PlanSection]:
    """나열형 섹션 전부."""
    return [build_tech_scope(structured), build_decisions(structured)]
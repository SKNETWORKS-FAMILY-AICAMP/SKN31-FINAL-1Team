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

from shared.schemas_base import Evidence

from .schemas import PlanSection, SectionType


def _ul(lines: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{escape(t)}</li>" for t in lines) + "</ul>"


def _ev(items: list[dict]) -> list[Evidence]:
    out = []
    for i in items:
        e = i.get("evidence")
        if e:
            out.append(Evidence(**e) if isinstance(e, dict) else e)
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
    evidence: list[Evidence] = []

    # ── 기술 스택 ────────────────────────────────────────────
    # technical 요구사항 + tech 결정. 내용이 같으면 한 번만 넣습니다.
    tech = reqs.get("technical", [])
    
    # seen = {t.get("content", "") for t in tech}
    # for d in decisions:
    #     if d.get("category") == "tech" and d.get("content") not in seen:
    #         tech.append(d)

    if tech:
        lines = [t["content"] for t in tech]
        parts.append("<p><strong>기술 스택</strong></p>" + _ul(lines))
        items += lines
        evidence += _ev(tech)

    # ── 성능·보안 요구 ───────────────────────────────────────
    nonfunc = reqs.get("non_functional", [])
    if nonfunc:
        lines = [n["content"] for n in nonfunc]
        parts.append("<p><strong>성능·보안 요구</strong></p>" + _ul(lines))
        items += lines
        evidence += _ev(nonfunc)

    # ── 데이터 요구 ──────────────────────────────────────────
    data_reqs = reqs.get("data", [])
    if data_reqs:
        lines = [d["content"] for d in data_reqs]
        parts.append("<p><strong>데이터 요구</strong></p>" + _ul(lines))
        items += lines
        evidence += _ev(data_reqs)

    # ── 제약사항 ─────────────────────────────────────────────
    # constraints는 type이 있고(일정/인력 등), scope 결정은 없습니다.
    scope: list[dict] = list(structured.get("constraints", []))
    scope += [d for d in decisions if d.get("category") == "scope"]

    if scope:
        lines = [
            (f"[{s['type']}] {s['content']}" if s.get("type") else s["content"])
            for s in scope
        ]
        parts.append("<p><strong>제약사항</strong></p>" + _ul(lines))
        items += lines
        evidence += _ev(scope)

    return PlanSection(
        no=6, key="tech_scope", title="기술 및 제약사항",
        section_type=SectionType.LIST,
        content_html="".join(parts),
        items=items,
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

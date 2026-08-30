"""
노드 ② 기획서 생성 — 실행.

  [1] 서술형 5개 생성       LLM (Instructor가 검증·재시도)
  [2] 나열형 2개 조립       코드
  [3] 섹션 정렬·병합        코드
  [4] is_incomplete 판정    코드
  [5] unresolved 전달       코드
"""

from shared.llm_client import get_client
from shared.retry_config import MAX_RETRIES, MAX_TOKENS, MODEL, PROVIDER, TEMPERATURE

from . import list_builder
from .prompts import (
    REGENERATE_PROMPT,
    SYSTEM_PROMPT,
    build_messages,
    build_regenerate_messages,
)
from .schemas import (
    SECTION_SPEC,
    PlanDocument,
    PlanSection,
    PlanSections,
    SectionType,
)

ALLOWED_TAGS = {"p", "ul", "li", "strong"}


def _call(system: str, messages: list[dict], response_model):
    """provider별 호출 차이를 흡수합니다."""
    client = get_client()
    common = dict(
        model=MODEL,
        response_model=response_model,
        max_retries=MAX_RETRIES,
        temperature=TEMPERATURE,
    )
    if PROVIDER == "anthropic":
        return client.messages.create(
            system=system, max_tokens=MAX_TOKENS, messages=messages, **common
        )
    return client.chat.completions.create(
        messages=[{"role": "system", "content": system}] + messages, **common
    )


def _source_is_empty(structured: dict, source_fields: list[str]) -> bool:
    """
    is_incomplete 판정 — 코드가 합니다.

    원본 필드가 비었는지는 len()으로 판정되는 '사실'입니다.
    LLM에 맡기면 "비어 있지만 그럴듯하게 채워버리는" 실패가 생깁니다.
    코드로 옮기면 그 실패 경로가 닫힙니다.
    """
    for field in source_fields:
        if "[" in field:                       # decisions[feature] 형태
            base, cat = field.split("[")
            cat = cat.rstrip("]")
            if any(d.get("category") == cat for d in structured.get(base, [])):
                return False
            continue

        cur = structured
        for part in field.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
            if cur is None:
                break
        if cur:                                # 값이 있고 빈 리스트/문자열이 아님
            return False
    return True


def run(structured: dict, proposal_id: str) -> PlanDocument:
    # ── [1] 서술형 5개 생성 ──────────────────────────────────
    result: PlanSections = _call(
        SYSTEM_PROMPT, build_messages(structured), PlanSections
    )
    by_key = {s.key: s for s in result.sections}

    # ── [2] 나열형 2개 조립 ──────────────────────────────────
    list_sections = {s.key: s for s in list_builder.build_all(structured)}

    # ── [3] 병합 + [4] is_incomplete 판정 ────────────────────
    sections: list[PlanSection] = []
    for spec in SECTION_SPEC:
        if spec["type"] == SectionType.LIST:
            sections.append(list_sections[spec["key"]])
            continue

        gen = by_key.get(spec["key"])
        content = gen.content_html if gen else ""

        sections.append(PlanSection(
            no=spec["no"],
            key=spec["key"],
            title=spec["title"],
            section_type=spec["type"],
            content_html=content,
            # 서술형은 문단이라 쪼갤 항목이 없습니다. 하류는 content_html을 씁니다.
            items=[],
            source_fields=spec["source_fields"],
            evidence=gen.evidence if gen else [],
            # 원본이 비었거나 LLM이 아무것도 못 쓴 경우
            is_incomplete=_source_is_empty(structured, spec["source_fields"])
            or not content.strip(),
        ))

    sections.sort(key=lambda s: s.no)

    return PlanDocument(
        proposal_id=proposal_id,
        meeting_id=structured.get("meeting_id", ""),
        status="draft",
        sections=sections,
        # ── [5] 구조화 단계의 unresolved를 그대로 전달 ───────
        # "회의에서 이건 안 정했구나"를 PM이 알아야 합니다.
        unresolved=structured.get("unresolved", []),
    )


def regenerate_section(
    structured: dict, section_key: str, reject_type: str, comment: str
) -> PlanSection:
    """
    게이트 A 반려 시 해당 섹션 하나만 재생성합니다.

    나열형 섹션(tech_scope, decisions)은 코드 조립이라 재생성해도
    같은 결과가 나옵니다. 게이트 A에서 반려 버튼을 주지 않으므로
    여기 들어올 일이 없습니다.
    """
    spec = next(s for s in SECTION_SPEC if s["key"] == section_key)
    if spec["type"] == SectionType.LIST:
        raise ValueError(
            f"{section_key}는 코드 조립 섹션이라 재생성 대상이 아닙니다. "
            "PM이 직접 수정하도록 하세요."
        )

    result: PlanSections = _call(
        SYSTEM_PROMPT + "\n\n" + REGENERATE_PROMPT,
        build_regenerate_messages(structured, section_key, reject_type, comment),
        PlanSections,
    )
    gen = next((s for s in result.sections if s.key == section_key), None)
    content = gen.content_html if gen else ""

    return PlanSection(
        no=spec["no"], key=spec["key"], title=spec["title"],
        section_type=spec["type"],
        content_html=content,
        items=[],
        source_fields=spec["source_fields"],
        evidence=gen.evidence if gen else [],
        # 반려 사유 중 원본 정보가 없어 못 채운 부분.
        # 작성자에게 그대로 보여주어 "왜 안 바뀌었는지"를 알립니다.
        needs_input=gen.needs_input if gen else "",
        is_incomplete=not content.strip(),
    )


# ─────────────────────────────────────────────────────────────
# 개발 중 단독 실행.
#     python -m meeting_analysis.node tests/fixtures/meeting_01.txt
#     python -m plan_draft.agent out/meeting_01.json
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    path = Path(sys.argv[1] if len(sys.argv) > 1 else "out/meeting_01.json")
    structured = json.loads(path.read_text(encoding="utf-8"))

    doc = run(structured, proposal_id=f"P-{path.stem}")

    out = Path("out")
    out.mkdir(exist_ok=True)
    (out / f"plan_{path.stem}.json").write_text(
        doc.model_dump_json(indent=2), encoding="utf-8"
    )

    print("=" * 62)
    for s in doc.sections:
        mark = "비어있음" if s.is_incomplete else f"{len(s.content_html)}자"
        kind = "LLM " if s.section_type == SectionType.NARRATIVE else "코드"
        print(f"  {s.no}. [{kind}] {s.title:22} {mark}")
    if doc.unresolved:
        print("\n[unresolved — PM 확인 필요]")
        for u in doc.unresolved:
            print(f"  · {u}")
    print("=" * 62)

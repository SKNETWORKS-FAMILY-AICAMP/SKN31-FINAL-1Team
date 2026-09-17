"""
노드 ② 기획서 생성 — 실행.

[1] 서술형 3개와 조건부 목표 생성             LLM
[2] 목록형 3개 섹션 조립                    코드
[2-1] 주요 기능 조립                         코드
[3] 섹션 정렬과 병합                       코드
[4] is_incomplete 판정                     코드
[5] unresolved 전달                        코드

실패 처리:
  _call()이 노드②의 유일한 LLM 호출 지점이다(run()·regenerate_section()
  둘 다 여기를 거친다). Instructor 재시도가 모두 소진되면
  InstructorRetryException이 올라오는데, 그대로 두면 호출부가 원인을
  구분 못 하고 뭉뚱그려 처리하게 되므로 여기서 로그를 남기고 원인별로
  구분된 NodeGenerationError로 다시 던진다. (호출부가 cause_code별로
  다른 안내문을 고르는 부분은 별도 작업 — shared/errors.py 참고.)
"""
import logging
from html import escape

from openai import APIError

try:
    from instructor.core import InstructorRetryException
except ImportError:  # 구버전 instructor 호환
    from instructor.exceptions import InstructorRetryException

from shared.errors import NodeGenerationError
from shared.llm_client import build_chat_kwargs, get_client, traceable
from shared.retry_config import MAX_RETRIES, MAX_TOKENS, MODEL, TEMPERATURE

from . import list_builder
from .feature_renderer import render_features
from .prompts import (
    REGENERATE_PROMPT,
    build_messages,
    build_regenerate_messages,
    build_system_prompt,
)
from .schemas import (
    SECTION_SPEC,
    PlanDocument,
    PlanSection,
    PlanSections,
    SectionType,
)

logger = logging.getLogger(__name__)

ALLOWED_TAGS = {"p", "ul", "li", "strong"}

# 2026-09-16: 서술형 섹션(1·2·4번)의 원본이 완전히 비어 있는데도 LLM이
# 다른 프로젝트 정보로 추정해 내용을 채운 경우 붙이는 표시입니다.
# 3번 섹션의 AI_SUGGESTED_GOAL_SUFFIX와 같은 목적(list_builder.py 참고)
# 이지만, 여긴 항목이 아니라 문단 전체이므로 문단 끝에 문장으로
# 붙입니다. LLM이 스스로 "이건 추정입니다"라고 신고하게 하지 않고
# _source_is_empty()로 코드가 판정한 사실에 따라 코드가 붙입니다 —
# LLM 자기 신고를 믿지 않는다는 이 프로젝트의 원칙과 같습니다.
AI_SUGGESTED_SECTION_NOTE = (
    "이 내용은 회의록에 직접 나오지 않아 다른 확인된 내용을 바탕으로 "
    "AI가 추정해 제안했습니다. PM 확인이 필요합니다."
)


def _mark_unverified_features(feats: list, structured: dict) -> None:
    """
    5번 주요 기능의 source_indices를 코드가 검증해 제자리에서 표시를 붙입니다.

    2026-09-16: feature_sources_for_citation은 verified 여부와 무관하게
    전부 넘깁니다(prompts.py 참고) — LLM이 어떤 기능 요구사항을 실제로
    참고했는지는 알아야 묶어 쓸 수 있기 때문입니다. 대신 그 인용이
    유효한지(검증된 항목만 인용했는지)는 LLM의 자기 신고가 아니라 여기서
    코드가 판정합니다 — DetailedGoal.matched_goal_index와 같은 원리입니다.

    인용 번호가 하나도 없거나, 범위를 벗어나거나, unverified 항목을
    가리키면 그 기능은 "근거 확인 필요"로 표시합니다(list_builder의
    UNVERIFIED_ITEM_SUFFIX 재사용 — 6·7번과 같은 의미: LLM이 실존하는
    항목을 썼지만 그 항목의 원문 검증 자체가 실패했다는 뜻입니다).

    2026-09-17: context_flag도 같은 방식으로 확인합니다. 인용 번호가
    유효하고(evidence_status=verified) 인용문이 원문에 있어도, 노드①의
    fact_check가 그 항목의 서술 자체를 의심스럽다고 표시했을 수 있습니다
    (list_builder._apply_context_flag과 같은 개념). 이 경고는
    feature_sources_for_citation에 인용 상태로만 실려 있어 여기서
    확인하지 않으면 조용히 사라집니다 — quote 기준으로 새로 추가한
    tech·scope 후보(build_feature_citation_sources 참고)에도 똑같이
    적용됩니다.
    """
    sources_by_index = {
        item["index"]: item
        for item in list_builder.build_feature_citation_sources(structured)
    }

    for feature in feats:
        indices = feature.source_indices

        all_verified = bool(indices) and all(
            idx in sources_by_index
            and sources_by_index[idx]["evidence_status"] == list_builder.VERIFIED
            for idx in indices
        )
        if not all_verified:
            feature.description = (
                feature.description + list_builder.UNVERIFIED_ITEM_SUFFIX
            )

        cited_flags = dict.fromkeys(
            sources_by_index[idx]["context_flag"]
            for idx in indices
            if idx in sources_by_index and sources_by_index[idx].get("context_flag")
        )
        for flag in cited_flags:
            feature.description = feature.description + (
                list_builder.CONTEXT_FLAG_SUFFIX_TEMPLATE.format(flag=flag)
            )


def _call(system: str, messages: list[dict], response_model, context: str = ""):
    """노드②의 유일한 LLM 호출 지점. 호출 인자 조립은 build_chat_kwargs()가
    모델 계열(gpt-4o / gpt-5)에 맞게 처리한다.

    context: 로그에 남길 짧은 설명(예: "run" 또는 재생성 대상 section_key).
    어떤 호출이 실패했는지 로그만 보고 알 수 있게 하기 위함이다.
    """
    try:
        client = get_client(MODEL)
        return client.chat.completions.create(
            **build_chat_kwargs(
                model=MODEL,
                messages=[{"role": "system", "content": system}] + messages,
                response_model=response_model,
                max_tokens=MAX_TOKENS,
                max_retries=MAX_RETRIES,
                temperature=TEMPERATURE,
            )
        )
    except InstructorRetryException as e:
        logger.exception(
            "노드② 기획서 생성 실패(%s) — 재시도 %s회 모두 스키마 검증 실패",
            context or "run", e.n_attempts,
        )
        raise NodeGenerationError(
            "AI가 기획서를 정해진 형식으로 생성하지 못했습니다"
            f"(재시도 {e.n_attempts}회 모두 실패). "
            "회의록 구조화 결과가 너무 짧거나 모호하지 않은지 확인해 주세요.",
            cause_code="LLM_RETRY_EXHAUSTED",
            node="plan_draft",
            original=e,
        ) from e
    except RuntimeError as e:
        # get_client()가 OPENAI_API_KEY 미설정 시 던지는 예외.
        logger.exception(
            "노드② 기획서 생성 실패(%s) — 설정 오류", context or "run",
        )
        raise NodeGenerationError(
            "AI 서비스 설정에 문제가 있어 기획서를 생성할 수 없습니다. "
            "관리자에게 문의해 주세요.",
            cause_code="CONFIG_ERROR",
            node="plan_draft",
            original=e,
        ) from e
    except APIError as e:
        logger.exception(
            "노드② 기획서 생성 실패(%s) — OpenAI API 호출 오류", context or "run",
        )
        raise NodeGenerationError(
            "AI 서비스 호출에 실패했습니다(네트워크 또는 서비스 오류). "
            "잠시 후 다시 시도해 주세요.",
            cause_code="LLM_API_ERROR",
            node="plan_draft",
            original=e,
        ) from e
    except Exception as e:
        logger.exception(
            "노드② 기획서 생성 실패(%s) — 알 수 없는 오류", context or "run",
        )
        raise NodeGenerationError(
            "기획서 생성 중 예상치 못한 오류가 발생했습니다.",
            cause_code="UNKNOWN",
            node="plan_draft",
            original=e,
        ) from e


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


@traceable(name="plan_draft.run")
def run(
    structured: dict,
    proposal_id: str,
    glossary_text: str = "",
    on_stage=None,
) -> PlanDocument:
    # on_stage: 있으면 각 내부 단계 시작 시 사람이 읽을 라벨(str)로 호출한다(선택,
    # develop 2026-09-15 — "기획서 초안 생성 중…" 하나로 뭉뚱그려져 있던 걸 세분화).
    def _stage(label: str) -> None:
        if on_stage:
            on_stage(label)

    # [1] 서술형 섹션과 세부 목표를 생성합니다.
    _stage("기획서 초안 작성 중…")
    result: PlanSections = _call(
        build_system_prompt(glossary_text),
        build_messages(structured, glossary_text),
        PlanSections,
        context=f"run proposal_id={proposal_id}",
    )

    by_key = {s.key: s for s in result.sections}

    # ── [2] 목록형 3개 조립 ──────────────────────────────────
    _stage("목록형 섹션 조립 중…")
    list_sections = {
        section.key: section
        for section in list_builder.build_all(
            structured,
            generated_goals=result.goals,
        )
    }

    # ── [3] 병합 + [4] is_incomplete 판정 ────────────────────
    _stage("섹션 병합 및 근거 매칭 중…")
    sections: list[PlanSection] = []
    for spec in SECTION_SPEC:
        if spec["type"] == SectionType.LIST:
            sections.append(list_sections[spec["key"]])
            continue

        # ── 5번 주요 기능은 features 배열로 별도 처리 ───────
        # 프론트가 항목 단위로 편집·삭제하므로 HTML 덩어리로 두면
        # 항목 하나만 고칠 수 없습니다.
        #
        # 2026-09-15: 노드①의 feature_name 태그로 코드가 기계적으로
        # 묶던 방식(list_builder.build_features)을 버렸습니다. 태그가
        # 청크마다 일관되지 않으면 "기타 기능 요구사항"에 항목이 뭉텅이로
        # 쏟아지는 문제가 실측으로 확인됐습니다. 이제 LLM이 검증된
        # functional_requirements·feature_decisions를 직접 묶어 쓴
        # result.features를 그대로 씁니다(schemas.py PlanSections.features).
        if spec["key"] == "features":
            feats = list(result.features)
            _mark_unverified_features(feats, structured)
            content = render_features(feats)
            # 무료 진단(LLM 재호출 없음): 검증됐지만 어떤 기능의
            # source_indices에도 인용되지 않은 기능 요구사항·결정이 있으면
            # PM에게 확인을 요청합니다(list_builder.ORPHANED_ITEMS_NOTE_TEMPLATE
            # 참고) — 노드①은 맞게 뽑았는데 노드②가 조용히 빠뜨렸을 수 있는
            # 경우입니다.
            #
            # 2026-09-17: needs_input 필드에만 담아뒀던 걸 content_html에도
            # 이어붙입니다. needs_input은 backend/meetings/services.py가
            # content_html만 꺼내 쓰고 이 필드를 읽지 않아 실제 화면에
            # 도달하지 않는 걸 확인했습니다(백엔드를 건드리지 않고 고칠 수
            # 있는 유일한 통로가 content_html — AI_SUGGESTED_SECTION_NOTE와
            # 같은 방식입니다). needs_input 필드 자체는 그대로 유지합니다.
            orphaned = list_builder.find_orphaned_feature_sources(feats, structured)
            needs_input_note = list_builder.orphaned_items_note(orphaned)
            if needs_input_note:
                content = content + f"<p>{escape(needs_input_note)}</p>"
            sections.append(PlanSection(
                no=spec["no"], key=spec["key"], title=spec["title"],
                section_type=spec["type"],
                content_html=content,
                features=feats,
                items=[f.title for f in feats],
                source_fields=spec["source_fields"],
                # LLM이 스스로 쓴 문장을 근거로 쓰지 않습니다. 노드①이
                # 검증한 원문을 섹션 전체 단위로 붙입니다(3·6·7번과 동일).
                evidence=list_builder.collect_feature_evidence(structured),
                needs_input=needs_input_note,
                is_incomplete=not feats,
            ))
            continue

        gen = by_key.get(spec["key"])
        content = gen.content_html if gen else ""

        # 2026-09-16: 원본이 완전히 비어 있는데 LLM이 그래도 내용을 썼다면
        # (다른 프로젝트 정보로 추정한 것) AI_SUGGESTED_SECTION_NOTE를
        # 붙입니다. LLM이 스스로 "이건 추정이다"라고 밝히길 기대하지
        # 않습니다 — _source_is_empty()가 이미 코드로 판정한 사실이므로
        # 그 결과에 따라 코드가 표시를 붙입니다.
        source_empty = _source_is_empty(structured, spec["source_fields"])
        if source_empty and content.strip():
            content = content + f"<p>{escape(AI_SUGGESTED_SECTION_NOTE)}</p>"

        sections.append(PlanSection(
            no=spec["no"],
            key=spec["key"],
            title=spec["title"],
            section_type=spec["type"],
            content_html=content,
            # 서술형은 문단이라 쪼갤 항목이 없습니다. 하류는 content_html을 씁니다.
            items=[],
            source_fields=spec["source_fields"],
            # 2026-09-07: gen.evidence(LLM이 스스로 인용한 근거, 원문 대조 안 됨)
            # 대신 노드①이 이미 검증해둔 원본 근거를 source_fields로 재수집합니다.
            # "근거 보기" 화면에서 verified/unverified를 신뢰성 있게 보여주려면
            # LLM의 자기 인용이 아니라 코드가 대조한 값이어야 합니다. 원본이
            # 비어 AI가 추정만 한 경우 이 목록은 자연히 비게 됩니다 — 추정
            # 내용을 뒷받침하는 검증된 원문이 없기 때문입니다.
            evidence=(
                list_builder.collect_core_goal_evidence(
                    structured,
                )
                if spec["key"] == "problem"
                else list_builder.collect_source_evidence(
                    structured,
                    spec["source_fields"],
                )
            ),
            # 2026-09-16: "원본이 비었으면 무조건 미완성"에서 "보여줄 내용이
            # 없으면 미완성"으로 바꿨습니다. 원본이 없어도 AI가 추정 초안을
            # 채웠으면 더 이상 미완성이 아닙니다 — 대신 AI_SUGGESTED_SECTION_NOTE
            # 표시로 검토가 필요하다는 걸 알립니다.
            is_incomplete=not content.strip(),
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
    spec = next(
        (
            item
            for item in SECTION_SPEC
            if item["key"] == section_key
        ),
        None,
    )

    if spec is None:
        raise ValueError(
            f"알 수 없는 섹션입니다: {section_key}"
        )

    if section_key not in {
        "overview",
        "problem",
        "users",
    }:
        raise ValueError(
            f"{section_key}는 코드 조립 섹션이라 재생성 대상이 아닙니다. "
            "PM이 직접 수정하도록 하세요."
        )

    result: PlanSections = _call(
        (
            build_system_prompt()
            + "\n\n"
            + REGENERATE_PROMPT
        ),
        build_regenerate_messages(
            structured,
            section_key,
            reject_type,
            comment,
        ),
        PlanSections,
        context=f"regenerate_section={section_key}",
    )
    gen = next((s for s in result.sections if s.key == section_key), None)
    content = gen.content_html if gen else ""

    return PlanSection(
        no=spec["no"], key=spec["key"], title=spec["title"],
        section_type=spec["type"],
        content_html=content,
        items=[],
        source_fields=spec["source_fields"],
        # run()과 동일한 이유로 gen.evidence 대신 검증된 원본 근거를 재수집합니다.
        evidence=list_builder.collect_source_evidence(structured, spec["source_fields"]),  # ⬅ 수정: 원래 evidence=gen.evidence if gen else [] 였음
        # 반려 사유 중 원본 정보가 없어 못 채운 부분.
        # 작성자에게 그대로 보여주어 "왜 안 바뀌었는지"를 알립니다.
        needs_input=gen.needs_input if gen else "",
        is_incomplete=not content.strip(),
    )


# ─────────────────────────────────────────────────────────────
# 개발 중 단독 실행.
#     python -m meeting_analysis.node tests/fixtures/meeting_01.txt
#     python -m plan_draft.agent out/meeting_01.json
#     python -m plan_draft.agent out/hotzone_test.json tests/fixtures/glossary_sample.txt
#                                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#                                          두 번째 인자(선택) — 용어집 텍스트 파일
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    path = Path(sys.argv[1] if len(sys.argv) > 1 else "out/meeting_01.json")
    structured = json.loads(path.read_text(encoding="utf-8"))
    glossary_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    glossary_text = (
        glossary_path.read_text(encoding="utf-8") if glossary_path else ""
    )
    print(f"[debug] glossary_text 길이: {len(glossary_text)}자")

    doc = run(structured, proposal_id=f"P-{path.stem}", glossary_text=glossary_text)

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
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
from shared.llm_client import build_chat_kwargs, get_client
from shared.retry_config import MAX_RETRIES, MAX_TOKENS, MODEL, TEMPERATURE

from . import list_builder
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


def run(
    structured: dict,
    proposal_id: str,
    glossary_text: str = "",
) -> PlanDocument:
    # [1] 서술형 섹션과 세부 목표를 생성합니다.
    result: PlanSections = _call(
        build_system_prompt(glossary_text),
        build_messages(structured, glossary_text),
        PlanSections,
        context=f"run proposal_id={proposal_id}",
    )

    by_key = {s.key: s for s in result.sections}

    # ── [2] 목록형 3개 조립 ──────────────────────────────────
    list_sections = {
    section.key: section
    for section in list_builder.build_all(
        structured,
        generated_goals=result.goals,)
    }

    # ── [3] 병합 + [4] is_incomplete 판정 ────────────────────
    sections: list[PlanSection] = []
    for spec in SECTION_SPEC:
        if spec["type"] == SectionType.LIST:
            sections.append(list_sections[spec["key"]])
            continue

        # ── 5번 주요 기능은 features 배열로 별도 처리 ───────
        # 프론트가 항목 단위로 편집·삭제하므로 HTML 덩어리로 두면
        # 항목 하나만 고칠 수 없습니다.
        if spec["key"] == "features":
            feats = list_builder.build_features(
                structured
            )
            # 읽기 모드용 HTML도 함께 만듭니다.
            # 편집은 features를, 표시는 content_html을 씁니다.
            content = "".join(
                f"<p><strong>{escape(f.title)}</strong></p>"
                f"<p>{escape(f.description)}</p>"
                for f in feats
            )
            sections.append(PlanSection(
                no=spec["no"], key=spec["key"], title=spec["title"],
                section_type=spec["type"],
                content_html=content,
                features=feats,
                items=[f.title for f in feats],
                source_fields=spec["source_fields"],
                # 기능 요구사항과 기능 결정사항에는 같은 기능이 표현만 다르게
                # 중복될 수 있습니다.
                #
                # 주요 기능 섹션에서는 requirements.functional의 근거를 우선
                # 사용하고, 기능 요구사항이 없을 때만 decisions[feature]를
                # 예비 근거로 사용합니다.
                #
                # 결정사항의 근거는 7번 최종 결정사항에서 별도로 표시됩니다.
                evidence=list_builder.collect_feature_evidence(structured),
                is_incomplete=not feats,
            ))
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
            # 2026-09-07: gen.evidence(LLM이 스스로 인용한 근거, 원문 대조 안 됨)
            # 대신 노드①이 이미 검증해둔 원본 근거를 source_fields로 재수집합니다.
            # "근거 보기" 화면에서 verified/unverified를 신뢰성 있게 보여주려면
            # LLM의 자기 인용이 아니라 코드가 대조한 값이어야 합니다.
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

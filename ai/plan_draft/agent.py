"""
노드 ② 기획서 생성 — 실행.

[1] 원문 사실·결정 인덱스 생성               LLM (장문만 청크 병렬)
[2] 1~7번 전체 기획서 단일 생성              LLM
[3] 원문 인용 검증·결정적 렌더링              코드
[4] 섹션 정합성·is_incomplete 판정            코드
[5] unresolved 전달                           코드

실패 처리:
  _call()이 노드②의 유일한 LLM 호출 지점이다(run()·regenerate_section()
  둘 다 여기를 거친다). Instructor 재시도가 모두 소진되면
  InstructorRetryException이 올라오는데, 그대로 두면 호출부가 원인을
  구분 못 하고 뭉뚱그려 처리하게 되므로 여기서 로그를 남기고 원인별로
  구분된 NodeGenerationError로 다시 던진다. (호출부가 cause_code별로
  다른 안내문을 고르는 부분은 별도 작업 — shared/errors.py 참고.)
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import escape
from typing import Literal

from openai import APIError

try:
    from instructor.core import InstructorRetryException
except ImportError:  # 구버전 instructor 호환
    from instructor.exceptions import InstructorRetryException

from shared import llm_instrumentation
from shared.errors import NodeGenerationError
from shared.llm_client import build_chat_kwargs, get_client, traceable
from shared.retry_config import MAX_RETRIES, MAX_TOKENS, MODEL, TEMPERATURE

from . import list_builder
from . import context_writer
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
FACT_INDEX_CHUNK_CHARS = 60_000
FULL_SOURCE_GENERATION_CHARS = 120_000


def _split_source_for_index(source: str, limit: int = FACT_INDEX_CHUNK_CHARS) -> list[str]:
    """문단 경계를 우선해 긴 회의록을 사실 색인용 구간으로 나눕니다."""
    paragraphs = [part.strip() for part in source.split("\n\n") if part.strip()]
    if not paragraphs:
        return [source.strip()] if source.strip() else []
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for paragraph in paragraphs:
        if len(paragraph) > limit:
            if current:
                chunks.append("\n\n".join(current))
                current, current_len = [], 0
            chunks.extend(
                paragraph[start:start + limit]
                for start in range(0, len(paragraph), limit)
            )
            continue
        extra = len(paragraph) + (2 if current else 0)
        if current and current_len + extra > limit:
            chunks.append("\n\n".join(current))
            current, current_len = [], 0
        current.append(paragraph)
        current_len += extra
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _build_planning_fact_index(source: str, proposal_id: str):
    chunks = _split_source_for_index(source)
    if not chunks:
        return context_writer.PlanningFactIndex()
    if len(chunks) == 1:
        indexes = [_call(
            context_writer.fact_index_system_prompt(),
            context_writer.fact_index_messages(chunks[0]),
            context_writer.PlanningFactIndex,
            context=f"run fact-index proposal_id={proposal_id}",
        )]
    else:
        with ThreadPoolExecutor(max_workers=min(4, len(chunks))) as executor:
            futures = [
                executor.submit(
                    _call,
                    context_writer.fact_index_system_prompt(),
                    context_writer.fact_index_messages(chunk, no, len(chunks)),
                    context_writer.PlanningFactIndex,
                    context=f"run fact-index {no}/{len(chunks)} proposal_id={proposal_id}",
                )
                for no, chunk in enumerate(chunks, start=1)
            ]
            indexes = [future.result() for future in futures]
    return context_writer.merge_verified_fact_indexes(indexes, source)

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

# 2026-09-17: 4번 대상 사용자 전용 표시입니다. AI_SUGGESTED_SECTION_NOTE는
# "원본이 아예 없을 때"만 붙는데, users는 실제 사용자가 있어도 니즈가
# 한두 줄뿐이라 화면이 얇아 보이는 문제가 있었습니다(실측: 무신사
# 회의록). 이 표시는 "사용자 자체는 실제로 확인됐지만, 설명 일부는
# 검증된 기능·데이터를 근거로 보완했다"는 뜻으로 위와는 다른 상황이라
# 문구도 다릅니다. NarrativeSection.source_indices가 비어 있지 않을
# 때 붙입니다. 번호의 유효성은 코드로 확인하지만 인용 선택은 모델 출력입니다.
USER_ENRICHMENT_NOTE = (
    "위 설명 중 일부는 회의에서 사용자가 직접 언급한 내용이 아니라, "
    "원문에서 확인된 서비스 목적·이용 행동·기능·데이터를 바탕으로 "
    "AI가 보완한 제안입니다. PM 확인이 필요합니다."
)


def _build_users_section(gen, structured: dict, spec: dict) -> PlanSection:
    """최초 생성과 재생성에 동일한 인용 검증과 확인 문구를 적용합니다."""
    content = gen.content_html if gen else ""
    cited = list(gen.source_indices or []) if gen else []
    sources = {s["index"]: s for s in list_builder.build_user_citation_sources(structured)}
    evidence = list_builder.collect_source_evidence(structured, spec["source_fields"])
    evidence += list_builder.collect_user_enrichment_evidence(cited, structured)
    notes = [gen.needs_input] if gen and gen.needs_input else []
    if any(idx not in sources for idx in cited):
        notes.append("사용자 설명의 인용 번호를 확인할 수 없습니다. 원문 대조가 필요합니다.")
    for idx in cited:
        source = sources.get(idx)
        if not source:
            continue
        if source.get("context_flag"):
            notes.append(f"사용자 설명 근거 검토: {source['context_flag']}")
        if source.get("statement_status") in {"proposed", "question", "rejected"}:
            notes.append("제안·질문·철회된 발언이 확정된 사용자 요구로 서술되지 않았는지 확인해 주세요.")
    if content.strip():
        if _source_is_empty(structured, spec["source_fields"]):
            content += f"<p>{escape(AI_SUGGESTED_SECTION_NOTE)}</p>"
        elif cited:
            content += f"<p>{escape(USER_ENRICHMENT_NOTE)}</p>"
        if notes:
            content += "<p><strong>PM 확인 사항</strong></p><ul>" + "".join(
                f"<li>{escape(note)}</li>" for note in dict.fromkeys(notes)
            ) + "</ul>"
    return PlanSection(
        no=spec["no"], key=spec["key"], title=spec["title"],
        section_type=spec["type"], content_html=content, items=[],
        source_fields=spec["source_fields"],
        evidence=list({e.quote: e for e in evidence}.values()),
        needs_input="\n".join(dict.fromkeys(notes)), is_incomplete=not content.strip(),
    )


def _mark_unverified_features(feats: list, structured: dict) -> tuple[list[str], list[str]]:
    """
    주요 기능의 근거 상태를 검증합니다.

    검토 문구를 description에 붙이면 본문을 읽기 어렵게 만드므로 설명은
    그대로 유지합니다. 모델이 context_flag를 바탕으로 구체적인 질문을 쓴
    feature.review_questions는 그대로 둡니다.

    2026-09-18: 코드가 붙이는 보수적인 문구(근거 미검증·과도한 확정)는
    더 이상 기능마다 하나씩 feature.review_questions에 넣지 않습니다.
    기능이 여러 개면 거의 같은 문장이 이름만 바뀐 채 5~6번 반복되어
    PM 확인 사항이 실제 결정 사항보다 boilerplate로 채워지는 문제가
    실측(무신사 회의록 웹 테스트)으로 확인됐습니다. 대신 영향받은 기능
    제목만 모아 반환하고, run()이 섹션 하단에 한 문장으로 묶어 보여줍니다.
    """
    sources_by_index = {
        item["index"]: item
        for item in list_builder.build_feature_citation_sources(structured)
    }

    unverified_titles: list[str] = []
    flagged_titles: list[str] = []

    for feature in feats:
        indices = feature.source_indices

        all_verified = bool(indices) and all(
            idx in sources_by_index
            and sources_by_index[idx]["evidence_status"] == list_builder.VERIFIED
            for idx in indices
        )
        if not all_verified:
            unverified_titles.append(feature.title)
        else:
            # 인용 자체는 유효하지만(citation 검증 통과) fact_check가 과도한
            # 확정 서술이라고 표시한 경우만 별도로 묻습니다 — 근거 미검증
            # 쪽이 더 근본적인 문제라 그쪽에만 묻고 중복으로 두 번 안 묻습니다.
            cited_flags = dict.fromkeys(
                sources_by_index[idx]["context_flag"]
                for idx in indices
                if idx in sources_by_index and sources_by_index[idx].get("context_flag")
            )
            if cited_flags:
                flagged_titles.append(feature.title)

        feature.review_questions = list(dict.fromkeys(
            question.strip() for question in feature.review_questions if question.strip()
        ))

    return unverified_titles, flagged_titles


def _call(system: str, messages: list[dict], response_model, context: str = ""):
    """노드②의 유일한 LLM 호출 지점. 호출 인자 조립은 build_chat_kwargs()가
    모델 계열(gpt-4o / gpt-5)에 맞게 처리한다.

    context: 로그에 남길 짧은 설명(예: "run" 또는 재생성 대상 section_key).
    어떤 호출이 실패했는지 로그만 보고 알 수 있게 하기 위함이다. 회의록
    원문이나 API 키는 절대 담지 않는다 — 계측 로그도 이 값을 그대로
    쓰므로 이 계약이 깨지면 계측 로그도 함께 깨진다.

    계측(llm_instrumentation): 프롬프트·모델·max_tokens·retry 설정에는
    전혀 관여하지 않는다. hooks는 instructor가 실제 API를 시도할 때마다
    호출하는 관찰용 콜백이라 재시도 횟수나 응답 내용에 영향을 주지 않는다.
    """
    started_at = datetime.now(timezone.utc)
    start_perf = time.perf_counter()
    call_hooks, attempt_counter = llm_instrumentation.make_call_hooks()
    try:
        client = get_client(MODEL)
        call_kwargs = build_chat_kwargs(
            model=MODEL,
            messages=[{"role": "system", "content": system}] + messages,
            response_model=response_model,
            max_tokens=MAX_TOKENS,
            max_retries=MAX_RETRIES,
            temperature=TEMPERATURE,
        )
        if call_hooks is not None:
            call_kwargs["hooks"] = call_hooks
        result = client.chat.completions.create(**call_kwargs)
    except InstructorRetryException as e:
        llm_instrumentation.record_call(llm_instrumentation.build_metrics(
            context=context or "run", model=MODEL, started_at=started_at,
            start_perf=start_perf,
            attempt_count=attempt_counter.count or getattr(e, "n_attempts", None),
            success=False, result=e, error_type="InstructorRetryException",
        ))
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
        llm_instrumentation.record_call(llm_instrumentation.build_metrics(
            context=context or "run", model=MODEL, started_at=started_at,
            start_perf=start_perf, attempt_count=attempt_counter.count or None,
            success=False, error_type="RuntimeError",
        ))
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
        llm_instrumentation.record_call(llm_instrumentation.build_metrics(
            context=context or "run", model=MODEL, started_at=started_at,
            start_perf=start_perf, attempt_count=attempt_counter.count or None,
            success=False, error_type="APIError",
        ))
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
        llm_instrumentation.record_call(llm_instrumentation.build_metrics(
            context=context or "run", model=MODEL, started_at=started_at,
            start_perf=start_perf, attempt_count=attempt_counter.count or None,
            success=False, error_type=type(e).__name__,
        ))
        logger.exception(
            "노드② 기획서 생성 실패(%s) — 알 수 없는 오류", context or "run",
        )
        raise NodeGenerationError(
            "기획서 생성 중 예상치 못한 오류가 발생했습니다.",
            cause_code="UNKNOWN",
            node="plan_draft",
            original=e,
        ) from e
    else:
        llm_instrumentation.record_call(llm_instrumentation.build_metrics(
            context=context or "run", model=MODEL, started_at=started_at,
            start_perf=start_perf, attempt_count=attempt_counter.count or 1,
            success=True, result=result,
        ))
        return result


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
    generation_strategy: Literal["parallel", "hybrid", "indexed", "direct"] = "parallel",
    on_fact_index=None,
) -> PlanDocument:
    # on_stage: 있으면 각 내부 단계 시작 시 사람이 읽을 라벨(str)로 호출한다(선택,
    # develop 2026-09-15 — "기획서 초안 생성 중…" 하나로 뭉뚱그려져 있던 걸 세분화).
    def _stage(label: str) -> None:
        if on_stage:
            on_stage(label)

    source = structured.get("plan_source_text") or ""
    contextual = bool(source.strip())
    if generation_strategy not in {"parallel", "hybrid", "indexed", "direct"}:
        raise ValueError(f"지원하지 않는 기획서 생성 전략: {generation_strategy}")
    messages = build_messages(structured, glossary_text)
    technical_draft = None
    whole_contextual = contextual and generation_strategy in {"indexed", "direct", "parallel"}
    if contextual and generation_strategy == "parallel":
        # 2026-09-21 인수인계 문서(PLAN_GENERATION_HANDOFF) 기준 운영 기본
        # 경로. 회의록 원문을 두 개의 독립된 LLM 호출로 나눠 동시에 실행한다
        # — 호출 A(1~5번: 개요·목표·세부목표·사용자·주요기능), 호출 B(6~7번:
        # 기술·최종 결정). 둘 다 원문 전체를 직접 읽으며, 구조화 노드나 별도
        # 사실 인덱스 LLM에 의존하지 않는다. 전체 단일 호출(WholePlanDraft)은
        # 기술·최종 결정이 다른 섹션에 밀려 누락되는 문제가 있었고, 사실
        # 인덱스 선행 호출(indexed)은 시간이 배로 들면서도 필수 결정을
        # 놓쳤다 — 그래서 관심사가 다른 두 호출로 쪼개고 병렬로 시간을
        # 합산하지 않는다.
        _stage("콘텐츠·기술 결정 병렬 생성 중…")
        with ThreadPoolExecutor(max_workers=2) as executor:
            content_future = executor.submit(
                _call,
                context_writer.content_plan_system_prompt(glossary_text),
                context_writer.content_plan_messages(source),
                context_writer.ContentPlanDraft,
                context=f"run content-plan proposal_id={proposal_id}",
            )
            technical_future = executor.submit(
                _call,
                context_writer.technical_decision_system_prompt(glossary_text),
                context_writer.technical_decision_messages(source),
                context_writer.TechnicalDecisionPlan,
                context=f"run technical-decisions proposal_id={proposal_id}",
            )
            content_draft = content_future.result()
            technical_draft = technical_future.result()
        if on_fact_index:
            on_fact_index(context_writer.PlanningFactIndex())
        result = content_draft.context
        feature_draft = content_draft.features
    elif contextual and generation_strategy == "hybrid":
        # 회의록 구조화 노드가 이미 검증한 사실·결정·근거를 탐색 지도로
        # 재사용합니다. 1~5번의 서술·의미 묶기만 LLM에 맡기고, 누락되면
        # 하류 요구사항까지 흔들리는 6~7번은 코드가 구조화 결과에서
        # 결정적으로 조립합니다. 별도 사실 인덱스 LLM은 호출하지 않습니다.
        #
        # 2026-09-21: 운영 기본값이 아니다(평가용으로만 남겨둔다). 이 경로는
        # structured에 project/users/requirements/decisions 같은 구조화
        # 데이터가 미리 채워져 있어야 하고, 빈 값이면 모든 섹션이 비게
        # 된다 — PLAN_GENERATION_HANDOFF 문서 2절 참고. 웹 경로는 더 이상
        # 이 값을 쓰지 않는다.
        _stage("기획서 핵심 섹션 작성 중…")
        result = _call(
            build_system_prompt(glossary_text),
            messages,
            PlanSections,
            context=f"run hybrid-plan proposal_id={proposal_id}",
        )
        if on_fact_index:
            on_fact_index(context_writer.PlanningFactIndex())
    elif whole_contextual:
        whole_draft = None
        if generation_strategy == "indexed":
            _stage("회의록 사실·결정 정리 중…")
            fact_index = _build_planning_fact_index(source, proposal_id)
        elif generation_strategy == "direct":
            # 비교 실험용 경로입니다. 운영 기본값은 parallel이며 바뀌지 않습니다.
            # 단일 호출이 짧고 정돈된 회의록에서 충분한지 같은 평가 기준으로
            # 측정하기 위해 빈 탐색 지도와 전체 원문만 전달합니다.
            fact_index = context_writer.PlanningFactIndex()
        else:
            raise ValueError(f"지원하지 않는 기획서 생성 전략: {generation_strategy}")
        if on_fact_index:
            on_fact_index(fact_index)
        if whole_draft is None:
            _stage("전체 기획서 작성 중…")
            whole_draft = _call(
                context_writer.whole_plan_system_prompt(glossary_text),
                context_writer.whole_plan_messages(
                    source,
                    fact_index,
                    include_full_source=len(source) <= FULL_SOURCE_GENERATION_CHARS,
                ),
                context_writer.WholePlanDraft,
                context=f"run whole-plan proposal_id={proposal_id}",
            )
        if generation_strategy == "indexed":
            whole_draft = context_writer.filter_nonfinal_outputs(whole_draft, fact_index)
        result = whole_draft.context
        feature_draft = whole_draft.features
        technical_draft = whole_draft.technical
    elif not contextual:
        _stage("기획서 초안 작성 중…")
        result = _call(
            build_system_prompt(glossary_text),
            messages,
            PlanSections,
            context=f"run proposal_id={proposal_id}",
        )

    by_key = (
        {
            "overview": result.overview,
            "problem": result.problem,
            "goals": result.goals,
            "users": result.users,
        }
        if whole_contextual
        else {s.key: s for s in result.sections}
    )

    # ── [2] 목록형 3개 조립 ──────────────────────────────────
    _stage("목록형 섹션 조립 중…")
    if whole_contextual:
        tech_section, decision_section = context_writer.render_technical_sections(
            technical_draft,
            source,
        )
        list_sections = {
            "tech_scope": tech_section,
            "decisions": decision_section,
        }
    else:
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
        if whole_contextual and spec["key"] in {"overview", "problem", "goals", "users"}:
            sections.append(context_writer.render_section(by_key[spec["key"]], source, spec))
            continue
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
        if spec["key"] == "features" and whole_contextual:
            sections.append(context_writer.render_features(list(feature_draft.features), source))
            continue

        if spec["key"] == "features":
            feats = list(result.features)
            unverified_titles, flagged_titles = _mark_unverified_features(feats, structured)
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
            section_review_questions = [needs_input_note] if needs_input_note else []
            # 2026-09-18: 기능마다 거의 같은 문구가 반복되지 않도록, 근거
            # 미검증·과도한 확정 두 유형을 기능별로 나누지 않고 섹션당
            # 한 문장으로 묶습니다(이름만 나열) — _mark_unverified_features
            # 주석 참고.
            if unverified_titles:
                section_review_questions.append(
                    "다음 기능은 인용 근거가 회의록 원문과 정확히 일치하지 않아 "
                    "확인이 필요합니다: " + ", ".join(dict.fromkeys(unverified_titles))
                )
            if flagged_titles:
                section_review_questions.append(
                    "다음 기능에 포함된 계획과 적용 기준이 최종 확정됐는지 "
                    "확인이 필요합니다: " + ", ".join(dict.fromkeys(flagged_titles))
                )
            content = render_features(feats, section_review_questions)
            all_review_questions = [
                question
                for feature in feats
                for question in feature.review_questions
            ] + section_review_questions
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
                needs_input="\n".join(dict.fromkeys(all_review_questions)),
                is_incomplete=not feats,
            ))
            continue

        # ── 4번 대상 사용자는 근거 보완 인용을 별도 처리 ────────
        #
        # 2026-09-17: users 배열에 실제 사용자가 있어도 니즈가 한두
        # 줄뿐이라 화면이 얇아 보이는 문제가 실측(무신사 회의록)으로
        # 확인됐습니다. NarrativeSection.source_indices에 담긴 번호를
        # 코드가 검증해, 실제로 검증된 기능·데이터를 근거로 보완한
        # 경우에만 표시를 붙이고 그 근거를 evidence에 추가합니다.
        if spec["key"] == "users":
            sections.append(_build_users_section(by_key.get("users"), structured, spec))
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
    if whole_contextual and technical_draft is not None:
        sections = context_writer.reconcile_sections(
            sections,
            technical_draft.decisions,
        )

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

    source = structured.get("plan_source_text") or ""
    if source.strip() and section_key in {"overview", "problem", "goals", "users"}:
        result = _call(
            context_writer.system_prompt()
            + f"\n재생성: sections/features 대신 key={section_key}인 섹션 객체 하나만 출력합니다.",
            build_regenerate_messages(structured, section_key, reject_type, comment),
            context_writer.SECTION_MODELS[section_key],
            context=f"regenerate_section={section_key}",
        )
        return context_writer.render_section(result, source, spec)

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
    if section_key == "users":
        return _build_users_section(gen, structured, spec)
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

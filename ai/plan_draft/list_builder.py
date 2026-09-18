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

# 2026-09-16: (근거 확인 필요)와 뜻이 다릅니다. 그건 "원문 대조는
# 했는데 검증에 실패했다"는 뜻이고, 이건 "애초에 회의에 없어서
# AI가 문맥으로 보완했다"는 뜻입니다(build_goals의
# matched_goal_index 처리 참고). 두 개념을 같은 문구로 섞으면 PM이
# "이게 왜 확인이 필요한지" 원인을 구분할 수 없습니다.
AI_SUGGESTED_GOAL_SUFFIX = " (AI 제안 · PM 확인 필요)"

# 2026-09-17: 문제에 대응하는 목표가 project.goals에 없을 때 쓰는 고정
# 문구입니다. 예전엔 이 경우 LLM이 "문제가 해소된 상태"를 지어내 썼는데,
# 실측(웹 테스트)에서 모든 항목이 "~하기 어렵다" -> "~할 수 있다"로
# 기계적으로 반전된 목표가 되는 문제가 확인됐습니다(plan_generation.yaml
# detailed_goal_rules 주석 참고). 지어낸 목표를 옮겨 쓰는 대신 "목표가
# 없다"는 사실 자체를 말합니다 — 아무것도 지어내지 않았으므로
# AI_SUGGESTED_GOAL_SUFFIX를 붙이지 않습니다.
GOAL_NOT_DISCUSSED_PLACEHOLDER = "이 문제에 대응하는 목표는 회의에서 논의되지 않았습니다."


def _mark_if_unverified(text: str, item: dict) -> tuple[str, bool]:
    """미확인 항목이면 표시를 붙입니다. (문장, 미확인 여부)를 반환합니다."""
    if _item_status(item) == VERIFIED:
        return text, False
    return text + UNVERIFIED_ITEM_SUFFIX, True


# 2026-09-17: (근거 확인 필요)와도 뜻이 다릅니다. 그건 "인용문이 원문에
# 있는지 확인 안 됨"이고, 이건 "인용문은 원문에 있는데(evidence_status=
# verified) 그 인용이 이 항목의 확정적인 서술을 실제로 뒷받침하는지
# 노드①의 meeting_analysis.fact_check가 의심스럽다고 표시한 것"입니다.
# 노드①이 항목에 붙인 item["context_flag"]를 그대로 옮겨 화면에
# 보여줍니다(list_builder.py는 새로 판정하지 않고 표시만 전달).
CONTEXT_FLAG_SUFFIX_TEMPLATE = " (원문 확인 필요 — {flag})"


def _apply_context_flag(text: str, item: dict) -> str:
    """meeting_analysis.fact_check가 붙인 context_flag가 있으면 표시를 덧붙입니다."""
    flag = item.get("context_flag")
    if not flag:
        return text
    return text + CONTEXT_FLAG_SUFFIX_TEMPLATE.format(flag=flag)


# 2026-09-18: 6·7번(기술 스택·최종 결정사항)의 content_html 전용 경고 생성.
#
# 위 _mark_if_unverified·_apply_context_flag는 본문 문장 뒤에 괄호로
# 경고를 이어붙인다. 1~5번은 이미 본문을 깨끗하게 두고 섹션 하단
# "PM 확인 사항"으로 모으도록 바꿨는데(context_writer.py, feature_renderer.py
# 참고), 6·7번은 code 조립 섹션이라 아직 옛 방식이 남아 있었다 — 실측
# (무신사 회의록 웹 테스트)에서 6번 본문에 "(원문 확인 필요 — 근거보다
# 과도하게 확정적으로 서술: ...)"가 그대로 섞여 나와 기획서가 완성된
# 문서처럼 안 읽히는 문제가 확인됐다. 여기서는 본문(text)은 그대로 두고
# 경고만 따로 뽑아 하단 블록으로 옮긴다.
#
# decisions(7번)의 items(태그 형식)는 node③이 파싱하므로 건드리지 않는다
# — 이 함수는 content_html에만 쓴다.
def _review_notes_for(text: str, item: dict) -> list[str]:
    """항목 본문 대신 섹션 하단에 보여줄 PM 확인 문구를 만듭니다."""
    notes: list[str] = []
    if _item_status(item) != VERIFIED:
        notes.append(f"'{text}'의 근거를 회의록 원문과 대조해 확인해 주세요.")
    flag = item.get("context_flag")
    if flag:
        notes.append(f"'{text}' — {flag}. 최종 확정 여부를 확인해 주세요.")
    return notes


def _review_html(notes: list[str]) -> str:
    notes = list(dict.fromkeys(note.strip() for note in notes if note.strip()))
    if not notes:
        return ""
    return "<p><strong>PM 확인 사항</strong></p><ul>" + "".join(
        f"<li>{escape(note)}</li>" for note in notes
    ) + "</ul>"


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

                # 2026-09-17: background_evidence_extra(리스트) — background
                # 한 문단에 사실이 여러 개면 노드①이 quote를 추가로 더
                # 낼 수 있습니다. background_evidence 하나만 쓰면 화면
                # 근거자료가 항상 1개로 보여 신뢰하기 어렵다는 문제를
                # 고치기 위해 추가했습니다(schemas.py Project 참고).
                extra_statuses = (
                    project.get("background_evidence_extra_status") or []
                )
                for i, extra in enumerate(
                    project.get("background_evidence_extra") or []
                ):
                    status = (
                        extra_statuses[i]
                        if i < len(extra_statuses)
                        else "unverified"
                    )
                    add(
                        {"evidence": extra, "evidence_status": status}
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


def build_feature_citation_sources(structured: dict) -> list[dict]:
    """
    5번 주요 기능 작성 재료를 번호 매겨 전부(verified+unverified) 반환합니다.

    2026-09-16: 예전엔 verified 항목만 걸러 LLM에게 보여줬습니다
    (prompts.py의 _verified_only). 그러면 노드①의 근거 검증이 한두
    글자 오차로 실패한(경우 B) 진짜 기능 요구사항이 LLM한테 보여지지도
    못하고 조용히 사라집니다 — 6·7번에서 이미 확인된 것과 같은 종류의
    침묵 실패입니다.

    이제 전부 번호를 매겨 넘기고, Feature.source_indices로 LLM이 어떤
    번호를 참고했는지 답하게 합니다(prompts.py는 이 함수 결과에서
    evidence_status·context_flag를 지운 index+content만 프롬프트에
    넣습니다 — LLM이 검증 상태를 보고 "안전한" 번호만 골라 인용하는 걸
    막기 위해서입니다). agent.py가 인용된 번호 중 unverified나
    context_flag가 섞여 있으면 해당 기능 설명에 표시를 붙입니다
    (build_goals의 matched_goal_index와 같은 원리 — 코드가 판정, LLM은
    후보만 제시).

    2026-09-17: decisions[tech]·decisions[scope] 중 인용문(quote)이
    functional·decisions[feature] 항목 정확히 하나와만 일치하는 것을
    후보에 추가합니다. 예를 들어 "결제는 카카오페이만 지원하고
    카드결제는 다음 버전으로 이관한다"가 scope로 분류돼 있어도, 같은
    quote를 쓰는 기능 요구사항이 정확히 하나면 그 기능 설명에 이 제약을
    반영할 재료로 씁니다. quote가 여러 기능에 걸치거나(공통 열거 문장)
    아예 없으면 후보에서 제외합니다 — "확인 가능할 때만 연결, 모호하면
    연결하지 않는다"는 기준을 quote 일치로 기계적으로 강제하는 것이고,
    실제로 연결할지는 여전히 LLM의 source_indices 인용 여부가 최종
    결정합니다(인용 안 하면 6·7번에만 남습니다 — 이 함수는 후보만
    넓힐 뿐 6·7번에서 항목을 빼지 않습니다).
    """
    requirements = structured.get("requirements") or {}
    functional = [
        item for item in (requirements.get("functional") or [])
        if isinstance(item, dict)
    ]

    all_decisions = [
        d for d in (structured.get("decisions") or [])
        if isinstance(d, dict)
    ]

    feature_decisions = [
        d for d in all_decisions if d.get("category") == "feature"
    ]

    primary_sources = functional + feature_decisions

    quote_counts: dict[str, int] = {}
    for item in primary_sources:
        key = _evidence_key(_evidence_quote(item))
        if key:
            quote_counts[key] = quote_counts.get(key, 0) + 1

    linked_decisions = [
        d for d in all_decisions
        if d.get("category") in ("tech", "scope")
        and quote_counts.get(_evidence_key(_evidence_quote(d)), 0) == 1
    ]

    return [
        {
            "index": i,
            "content": str(item.get("content", "")),
            "evidence_status": _item_status(item),
            "context_flag": item.get("context_flag") or "",
        }
        for i, item in enumerate(primary_sources + linked_decisions)
    ]


# 2026-09-17: 4번 대상 사용자 설명 보완용 재료.
#
# users 배열 자체는 이미 검증된 사용자 발언 그대로 프롬프트에 그대로
# 전달됩니다 — 여기서 다시 다루지 않습니다. 이 함수는 users에는 없지만
# 이미 확인된 사용자와 관련된 기능·데이터 및 user_signals의 원문 단서를
# 번호 매겨 후보로 제공합니다. 인용 존재 여부와 발언 상태는 별개입니다
# (NarrativeSection.source_indices, prompts.py user_sources_for_citation
# 참고).
#
# verified 항목만 보여줍니다 — 이건 핵심 추출(6·7번, 기능)과 달리
# "있으면 좋은" 보완 자료라, 근거 검증에 실패한 항목까지 넓혀 노출할
# 이유가 없습니다. 놓쳐도 사용자 프로필이 사라지는 게 아니라 그냥 그
# 문장만 덜 풍부해질 뿐입니다.
def build_user_citation_sources(structured: dict) -> list[dict]:
    requirements = structured.get("requirements") or {}
    functional = [
        item for item in (requirements.get("functional") or [])
        if isinstance(item, dict)
    ]
    data = [
        item for item in (requirements.get("data") or [])
        if isinstance(item, dict)
    ]

    sources = [
        {
            "index": i,
            "content": str(item.get("content", "")),
            "quote": _evidence_quote(item),
            "kind": "requirement",
            "actor": "",
            "statement_status": "stated",
            "context_flag": item.get("context_flag") or "",
        }
        for i, item in enumerate(_verified_items(functional + data))
    ]
    for item in structured.get("user_signals") or []:
        if not isinstance(item, dict) or item.get("evidence_status") != VERIFIED:
            continue
        if item.get("statement_status") not in {"stated", "proposed", "question", "rejected"}:
            continue
        if not _evidence_quote(item):
            continue
        sources.append({
            "index": len(sources),
            "content": str(item.get("content", "")),
            "quote": _evidence_quote(item),
            "kind": item.get("kind", ""),
            "actor": item.get("actor", ""),
            "statement_status": item["statement_status"],
            "context_flag": item.get("context_flag") or "",
        })
    return sources


def collect_user_enrichment_evidence(
    cited_indices: list[int],
    structured: dict,
) -> list[VerifiedEvidence]:
    """
    users 설명 보완에 실제로 인용된 번호의 원문 근거를 모읍니다.

    build_user_citation_sources가 verified 항목만 내놓으므로, 여기서
    찾은 근거는 전부 status="verified"입니다. 존재하지 않는 번호(잘못된
    인용)는 조용히 무시합니다 — 근거 없이 억지로 채우지 않습니다.
    """
    sources = {
        s["index"]: s for s in build_user_citation_sources(structured)
    }
    out: list[VerifiedEvidence] = []
    for idx in cited_indices:
        source = sources.get(idx)
        if source and source["quote"]:
            out.append(VerifiedEvidence(quote=source["quote"], status=VERIFIED))
    return _dedupe_evidence(out)


# 2026-09-16: LLM 호출을 추가하지 않는(무료) 진단입니다.
#
# source_indices/matched_goal_index 인프라는 이미 "LLM이 어떤 번호를
# 인용했는가"를 알고 있습니다. 검증된 항목인데 어떤 출력에서도 인용되지
# 않은 게 있으면, 그건 노드①이 맞게 뽑았는데 노드②가 조용히 빠뜨린
# 것일 수 있습니다 — 지금까지 고친 "검증 실패라 사라짐" 부류와는 다른,
# "검증은 됐는데 아무도 인용을 안 해서 빠짐" 부류의 침묵 실패입니다.
#
# 항목 수가 늘었다고 품질이 좋아진 게 아니듯, 미인용이 있다고 무조건
# 잘못된 것도 아닙니다(LLM이 여러 검증된 항목을 하나의 기능/목표로
# 정당하게 묶었을 수 있습니다). 그래서 이 표시는 "PM이 원문과 대조해
# 누락이 아닌지 확인하라"는 신호일 뿐, is_incomplete을 올리거나 항목을
# 지어내 채우지 않습니다.
ORPHANED_ITEMS_NOTE_TEMPLATE = (
    "다음은 회의록에서 근거가 확인됐지만 위 내용에 인용되지 않았습니다. "
    "누락이 아닌지 원문과 대조해 확인해 주세요: {items}"
)


def orphaned_items_note(contents: list[str]) -> str:
    """미인용 검증 항목이 있으면 확인 문구를, 없으면 빈 문자열을 반환합니다."""
    if not contents:
        return ""
    return ORPHANED_ITEMS_NOTE_TEMPLATE.format(items="; ".join(contents))


def find_orphaned_feature_sources(
    feats: list,
    structured: dict,
) -> list[str]:
    """
    검증됐지만 어떤 Feature.source_indices에도 인용되지 않은
    functional_requirements·feature_decisions의 원문 내용을 반환합니다.
    """
    sources = build_feature_citation_sources(structured)
    cited: set[int] = set()

    for feature in feats:
        for idx in getattr(feature, "source_indices", None) or []:
            cited.add(idx)

    return [
        source["content"]
        for source in sources
        if source["evidence_status"] == VERIFIED and source["index"] not in cited
    ]


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
    problems = []
    for item in _verified_items(project.get("problem_items") or []):
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        problems.append(_apply_context_flag(content, item))

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

    2026-09-16: project.problem_items·project.goals가 둘 다 verified
    항목 없이 완전히 비어 있으면, generated_goals에 뭐가 들어있든 무시하고
    바로 폴백으로 보냅니다. 실측(Codex 재현)에서 이 경우에도 LLM이 낸
    title/problem/goal을 그대로 받아들여 is_incomplete=False, evidence=[]로
    처리한 사례를 확인했습니다 — 근거가 0건인데 "완료된 섹션"으로
    보이는 건 이 섹션의 신뢰 전제(화면의 근거자료는 노드①이 검증한
    원문이다) 자체를 깨는 것이라 프롬프트 규칙만으로는 못 막습니다.

    2026-09-16: matched_goal_index로 목표 문장의 출처를 code가 검증합니다.
    LLM에게 목표 문장을 옮겨 적게 하는 대신 project.goals 번호만 답하게
    하고(prompts.py goals_for_citation, plan_generation.yaml
    matched_goal_index_rules), 번호가 실제로 유효하면(0 <= idx <
    검증된 목표 개수) 화면에 보여줄 목표 문장 자체를 그 목표의 원문으로
    코드가 덮어씁니다 — LLM이 옮겨 적다 생기는 오차 위험이 이 경로에는
    없습니다.

    2026-09-17: matched_problem_index를 problem 쪽에도 같은 방식으로
    적용합니다 — 이유는 matched_goal_index와 같습니다(schemas.py
    DetailedGoal 주석 참고). 번호가 유효하면 problem 문장도 원문으로
    덮어쓰고, 그 원문 항목의 context_flag(사실 검토 경고)를 이어
    붙입니다. matched_goal_index가 유효한 경우도 마찬가지로 그 목표
    항목의 context_flag를 goal 문장에 이어 붙입니다 — 이전에는 인용
    번호가 유효하다는 것만 확인하고 context_flag는 확인하지 않아서,
    "인용문이 원문에 있다"가 "그 항목의 서술이 실제로 맞다"는 뜻이
    아닌데도 경고가 조용히 사라졌습니다.

    번호가 없거나 범위를 벗어난 goal은 이제 LLM이 쓴 문장을 그대로
    받아들이되 AI_SUGGESTED_GOAL_SUFFIX 표시를 붙입니다 — "회의에 없던
    걸 AI가 보수적으로 제안했다"는 뜻입니다. 부정 반전 재발을 막는
    가드레일(임의 KPI·일정·권한 신설 금지, 문제 반전 금지)은
    plan_generation.yaml detailed_goal_rules의 프롬프트 규칙이 맡습니다
    — 이 함수는 LLM이 실제로 낸 텍스트를 신뢰하는 대신 표시만 붙입니다.
    """
    source_fields = [
        "project.problem",
        "project.problem_items",
        "project.goals",
    ]

    project = structured.get("project") or {}
    verified_problems = _verified_items(project.get("problem_items") or [])
    verified_goals = _verified_items(project.get("goals") or [])
    has_verified_source = bool(verified_problems) or bool(verified_goals)

    if not has_verified_source:
        return _build_goals_problem_only(structured, source_fields)

    items_out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    cited_goal_indices: set[int] = set()

    for generated_goal in generated_goals or []:
        if hasattr(generated_goal, "model_dump"):
            goal_data = generated_goal.model_dump()
        elif isinstance(generated_goal, dict):
            goal_data = generated_goal
        else:
            continue

        title = str(goal_data.get("title", "")).strip()
        problem = str(goal_data.get("problem", "")).strip()

        # title·problem이 비어 있으면 완전한 항목이 아니므로 제외합니다.
        # goal은 LLM 텍스트를 그대로 신뢰하지 않고 아래에서 코드가
        # 최종 결정하므로 여기서는 확인하지 않습니다.
        if not title or not problem:
            continue

        matched_problem_index = goal_data.get("matched_problem_index")
        if isinstance(matched_problem_index, int) and 0 <= matched_problem_index < len(verified_problems):
            problem_source = verified_problems[matched_problem_index]
            problem = (
                str(problem_source.get("content", "")).strip() or problem
            )
            problem = _apply_context_flag(problem, problem_source)

        matched_index = goal_data.get("matched_goal_index")
        if isinstance(matched_index, int) and 0 <= matched_index < len(verified_goals):
            # 번호가 유효하면 LLM이 쓴 문장을 버리고 원문으로 교체합니다 —
            # "회의 기반"이라고 표시할 내용은 실제로 회의 원문이어야 합니다.
            goal_source = verified_goals[matched_index]
            goal = (
                str(goal_source.get("content", "")).strip()
                or GOAL_NOT_DISCUSSED_PLACEHOLDER
            )
            goal = _apply_context_flag(goal, goal_source)
            is_ai_suggested = False
            cited_goal_indices.add(matched_index)
        else:
            # 2026-09-17: 대응하는 목표가 없을 때 LLM이 쓴 goal 텍스트를
            # 조건부로 받아들입니다. 이전에는(실측에서 plan_generation.yaml의
            # 옛 지시 "문제가 해소된 상태를 서술"을 따라 모든 항목이
            # "~하기 어렵다" -> "~할 수 있다"로 기계적으로 반전되는 문제가
            # 확인돼) 이 경로의 LLM 텍스트를 아예 버리고 고정 문구로만
            # 대체했습니다. 이제 plan_generation.yaml에 반전 금지·임의
            # KPI·일정·권한 신설 금지 가드레일을 명시한 뒤, LLM이 낸
            # 제안 문장을 AI_SUGGESTED_GOAL_SUFFIX 표시와 함께 그대로
            # 씁니다 — LLM이 빈 문자열을 내면(원문 부족을 자인) 여전히
            # 고정 문구로 대체합니다.
            goal = str(goal_data.get("goal", "")).strip() or GOAL_NOT_DISCUSSED_PLACEHOLDER
            is_ai_suggested = goal != GOAL_NOT_DISCUSSED_PLACEHOLDER

        key = (_norm(problem), _norm(goal))

        if key in seen:
            continue

        seen.add(key)
        items_out.append({
            "title": title,
            "problem": problem,
            "goal": goal,
            "is_ai_suggested": is_ai_suggested,
        })

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
                AI_SUGGESTED_GOAL_SUFFIX if item["is_ai_suggested"] else "",
                "</p>",
                "</li>",
            ]
        )
        for item in items_out
    ]

    # 무료 진단(LLM 재호출 없음): 검증됐지만 어떤 세부 목표에도 인용되지
    # 않은 project.goals 원문이 있으면 PM에게 확인을 요청합니다
    # (ORPHANED_ITEMS_NOTE_TEMPLATE 주석 참고).
    orphaned = [
        str(verified_goals[i].get("content", "")).strip()
        for i in range(len(verified_goals))
        if i not in cited_goal_indices
    ]
    needs_input_note = orphaned_items_note(orphaned)

    # 2026-09-17: needs_input 필드에만 담던 걸 content_html에도 이어붙입니다.
    # backend/meetings/services.py가 content_html만 꺼내 쓰고 needs_input은
    # 읽지 않아, 이 필드만으로는 화면에 절대 표시되지 않는 걸 확인했습니다.
    # 필드는 하류(needs_input을 참고할 수 있는 다른 경로)를 위해 그대로 둡니다.
    content_html = (
        "<ul>" + "".join(html_items) + "</ul>"
        + (f"<p>{escape(needs_input_note)}</p>" if needs_input_note else "")
    )

    items = [
        "\n".join(
            [
                item["title"],
                f"문제: {item['problem']}",
                "목표: "
                + item["goal"]
                + (AI_SUGGESTED_GOAL_SUFFIX if item["is_ai_suggested"] else ""),
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
        needs_input=needs_input_note,
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
    review_notes: list[str] = []

    def add(title: str, sources: list[dict], render) -> None:
        """
        항목을 조립하고 이미 나온 문장은 제외합니다.

        unverified·context_flag 항목도 지우지 않고 포함하되, 본문에 괄호로
        경고를 붙이지 않고 섹션 하단 PM 확인 사항으로 모읍니다
        (_review_notes_for 참고).
        """
        lines, used = [], []
        for s in sources:
            if not isinstance(s, dict):
                continue
            text = render(s)
            key = _norm(text)
            if not key or key in seen_lines:
                continue
            seen_lines.add(key)
            review_notes.extend(_review_notes_for(text, s))
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

    # 2026-09-17: needs_input 필드에만 담던 걸 content_html에도 이어붙입니다
    # (build_goals와 같은 이유 — backend/meetings/services.py가 needs_input을
    # 읽지 않아 이 필드만으로는 화면에 도달하지 않습니다).
    review_notes = list(dict.fromkeys(review_notes))
    content_html = "".join(parts) + _review_html(review_notes)

    return PlanSection(
        no=6, key="tech_scope", title="기술 스택 및 제약사항",
        section_type=SectionType.LIST,
        content_html=content_html,
        items=items,
        groups=groups,
        source_fields=[
            "requirements.technical", "requirements.non_functional",
            "requirements.data", "decisions[tech]",
            "constraints",
        ],
        evidence=_dedupe_evidence(evidence),
        is_incomplete=not parts,
        needs_input="\n".join(review_notes),
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

    2026-09-17: content_html과 items를 분리했습니다. items는 지금까지
    써온 "[기능] 내용" 형태를 그대로 유지합니다 — ai/requirement_draft
    (node③, 다른 팀원 담당)의 field_roles.yaml이 이 문자열 안의
    "[기능]"/"[기술]"/"[범위]" 태그를 직접 파싱해 범위 결정을 요구사항화
    하지 않도록 걸러내고 있어서(TAG_GATED 규칙), 이 형식을 바꾸면 node③이
    조용히 깨집니다. 반면 content_html(화면 표시 전용, 하류가 안 씀)은
    모든 줄 앞에 같은 대괄호 태그가 반복되어 로그처럼 읽히는 문제가 있어,
    tech_scope(6번)처럼 카테고리별 소제목으로 묶어서 사람이 읽기 좋게
    다시 만듭니다. 두 표현 다 같은 lines(태그 있는 문자열)에서 만드므로
    내용 자체는 완전히 같습니다.
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
    subtitle = {
        "feature": "기능 관련 결정",
        "non_functional": "비기능 관련 결정",
        "data": "데이터 관련 결정",
        "tech": "기술 관련 결정",
        "scope": "범위 관련 결정",
    }

    items: list[str] = []
    by_category: dict[str, list[str]] = {}
    review_notes: list[str] = []

    for d in decisions:
        category = d["category"]
        rationale_suffix = f" (이유: {d['rationale']})" if d.get("rationale") else ""

        # items: node③이 파싱하는 태그 형식. 바꾸지 않습니다.
        tagged_text = f"[{label.get(category, category)}] {d['content']}{rationale_suffix}"
        tagged_text, _ = _mark_if_unverified(tagged_text, d)
        tagged_text = _apply_context_flag(tagged_text, d)
        items.append(tagged_text)

        # content_html: 화면 표시 전용. 태그 대신 소제목으로 묶고, 경고는
        # 본문에 붙이지 않고 섹션 하단 PM 확인 사항으로 모읍니다.
        plain_text = f"{d['content']}{rationale_suffix}"
        review_notes.extend(_review_notes_for(plain_text, d))
        by_category.setdefault(category, []).append(plain_text)

    parts = [
        f"<p><strong>{subtitle.get(category, category)}</strong></p>" + _ul(lines)
        for category, lines in by_category.items()
    ]

    review_notes = list(dict.fromkeys(review_notes))
    content_html = "".join(parts) + _review_html(review_notes)

    return PlanSection(
        no=7, key="decisions", title="최종 결정사항",
        section_type=SectionType.LIST,
        content_html=content_html,
        items=items,
        source_fields=["decisions"],
        evidence=_dedupe_evidence(_ev(decisions)),
        needs_input="\n".join(review_notes),
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

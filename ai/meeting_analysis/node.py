"""
노드 1 회의록 구조화 실행.

검증 순서:
  0. 개발 관련성 판별
  1. 스키마 검증
  2. Evidence 원문 검증
  3. 교차 규칙 검증

개발과 무관하거나 개발 의도를 판단하기 어려운 회의는
구조화와 기획서 생성을 진행하지 않습니다.

개발 관련 내용과 무관한 내용이 섞여 있으면
개발 관련 원문만 구조화 단계에 전달합니다.

## 2026-09-16: 길이 기준 하이브리드로 재도입

09-15에 청크 분할을 껐던 이유는 두 가지였습니다 — (a) 청크마다 같은
기능을 다른 feature_name으로 불러 "기타 기능 요구사항"이 쌓이는 문제,
(b) 같은 사실이 표현만 바뀐 채 중복 등록되는 문제(정확 일치 기반
중복 제거로는 못 잡음).

그런데 (a)는 이미 같은 날 다른 변경으로 해소됐습니다 — plan_draft가
feature_name으로 기계적으로 묶던 방식(list_builder.build_features)을
버리고, 검증된 functional 요구사항을 LLM이 통째로 보고 직접 묶어
쓰도록 바뀌었습니다(plan_draft/schemas.py PlanSections.features 참고).
즉 청크마다 feature_name이 달라져도 더 이상 문제가 되지 않습니다.

(b)는 부분적으로만 고쳤습니다 — 정확 일치 대신 정규화한 문자열의
유사도(difflib, 임계값 0.82)로 중복을 판정합니다(_is_duplicate 참고).
"스토리지랑 AWS, RDS를 나눠서..."와 "네. 스토리지랑 AWS, RDS를
나눠서..."처럼 어두 표현·조사·어미만 다른 문장은 이제 같은 항목으로
잡힙니다(실측 확인). 다만 "원본은 S3에 저장" vs "원본 데이터는
오브젝트 스토리지에 적재"처럼 아예 다른 단어를 쓰는 의미상 중복은
difflib 문자 단위 유사도로는 여전히 못 잡습니다 — 이건 의미를 이해해야
하는 문제라 LLM 없이는 풀리지 않습니다.

이 잔여 위험은 구조적으로 줄여뒀습니다 — overview(전체 원문 통짜 호출)
결과를 exhaustive 필드 병합에서 아예 제외합니다(_merge_extractions
참고). 09-15에 관찰된 표현 차이 중복은 상당수가 "청크가 뽑은 문장"과
"overview가 같은 내용을 자기 말로 다시 쓴 문장"의 충돌이었는데,
overview를 애초에 후보에서 빼면 이 충돌 자체가 안 생깁니다. 남는
위험은 화자가 같은 사실을 회의 중 서로 다른 시점(=서로 다른 청크)에
다른 단어로 반복 언급하는 경우뿐이고, 이건 09-15 관찰보다 좁은
범위입니다. 이후에도 이런 중복이 반복 확인되면 그때 LLM 기반 의미
병합을 추가하세요 — 지금은 비용·복잡도 대비 근거가 부족해 넣지
않았습니다.

두 원인의 위험을 충분히 줄였다고 보고, 청크 분할의 장점(회수율)을
다시 씁니다. 다만 짧은 회의록에서는 청크 호출 자체가 불필요한
비용·시간이므로, CHUNK_TRIGGER_CHARS(원문 관련 부분 기준)를 넘는
회의록에만 청크+병합을 적용하고 그 이하는 기존처럼 단일 호출을
씁니다. 이 값은 2026-09-16 실측 재현(29,372자 회의록에서 후반부 주제가
누락되는 실행이 관찰됨)을 근거로 그보다 충분히 낮게 잡았습니다 — 짧은
회의록의 "정리된 문서" 품질은 그대로 지키면서, 긴 회의록에서 반복
확인된 회수율 변동 문제만 겨냥합니다.

청크별 호출과 전체 원문 통짜 호출은 서로 결과가 독립적이라 순서대로
부를 이유가 없습니다. STRONG_MODEL 호출 하나가 실측 100~140초라, 청크
10개짜리 회의록을 순서대로 부르면 20분을 넘겨 동기 응답을 기다리는
요청으로는 못 씁니다. _extract_structured가 ThreadPoolExecutor로
전부 동시에 부릅니다 — I/O 대기가 대부분이라 스레드로 충분합니다.
"""

import difflib
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from openai import APIError

try:
    from instructor.core import InstructorRetryException
except ImportError:
    from instructor.exceptions import InstructorRetryException

from shared.errors import NodeGenerationError
from shared.llm_client import build_chat_kwargs, get_client, traceable
from shared.retry_config import (
    MAX_RETRIES,
    MAX_TOKENS,
    MODEL,
    STRONG_MODEL,
    STRONG_MODEL_MAX_TOKENS,
    TEMPERATURE,
)

from .chunking import chunk_meeting_text
from .coverage_check import check_coverage
from .eligibility import (
    MeetingEligibilityError,
    assess_meeting,
)
from .prompts import (
    build_messages,
    build_system_prompt,
)
from .schemas import (
    MeetingExtraction,
    MeetingStructured,
)
from .validators import cross_rules
from .validators.evidence import (
    EvidenceReport,
    format_report,
    normalize,
    verify_and_mark,
)


logger = logging.getLogger(__name__)

# 이 길이를 넘는 관련 원문(assess_meeting이 걸러낸 이후 기준)에만
# 청크+병합을 적용합니다. 짧은 회의록까지 청크로 나누면 09-15에 확인된
# "정리 안 된 문서" 문제가 다시 생깁니다.
CHUNK_TRIGGER_CHARS = 12000

REQUIREMENT_CATEGORIES = (
    "functional",
    "non_functional",
    "data",
    "technical",
)

# _is_duplicate의 유사도 임계값. normalize()로 공백·문장부호를 지운
# 문자열 기준입니다 — 어미나 조사 몇 글자 차이는 넘기고, 서로 다른
# 사실은 걸러내는 지점을 실측 없이 보수적으로 잡았습니다. 오탐(서로 다른
# 항목이 같다고 판정됨)이 보이면 올리고, 미탐(표현만 다른 중복이
# 안 잡힘)이 보이면 내리세요.
_SIMILARITY_THRESHOLD = 0.82

# 2026-09-16: 유사도만으로는 문장 앞머리의 행위자(주체)가 바뀐 경우를 못
# 잡습니다. 실측(Codex 재현)에서 "관리자는 회의록을 삭제할 수 있다"와
# "참여자는 회의록을 삭제할 수 있다"가 ratio 0.857로 같은 항목 취급되어
# 하나가 삭제됐습니다 — 둘은 권한 범위가 다른 별개 요구사항인데도요.
#
# 처음엔 "조사(는/은/이/가) 앞까지를 주어로 본다"는 방식을 시도했는데,
# "적재하는"처럼 서술어 어미에도 같은 글자가 흔히 섞여 있어 문장 앞부분이
# 아니라 훨씬 뒤에서 걸려 오히려 정상 케이스(예: "네."만 붙은 필러 접두)
# 까지 별개로 오판했습니다. 대신 "한쪽이 다른 쪽의 완전한 뒷부분인가"로
# 판정합니다 — "네. 스토리지랑..."은 "스토리지랑..."의 앞에 짧은 필러만
# 붙은 것이라 뒷부분이 통째로 일치하지만, "관리자는..."과 "참여자는..."은
# 길이가 같은데 앞부분 내용 자체가 달라 뒷부분(는~있다)만 부분적으로
# 겹칠 뿐 한쪽이 다른 쪽을 통째로 포함하지 않습니다.
def _same_leading_subject(a: str, b: str) -> bool:
    """짧은 쪽이 긴 쪽의 완전한 접미사인지(=짧은 접두어 차이뿐인지) 봅니다."""
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return longer.endswith(shorter)


def _dedupe_key(*parts: str) -> str:
    """중복 판정용 정규화 키. 지정한 필드들을 이어 붙여 비교합니다."""
    return normalize("".join(str(part or "") for part in parts))


def _is_duplicate(key: str, seen_keys: list[str]) -> bool:
    """
    key가 seen_keys 중 하나와 같은 내용을 가리키는지 판정합니다.

    정확 일치뿐 아니라 유사도도 봅니다 — 청크가 나뉘면 같은 발언을
    가리키는 문장이 청크마다 표현이 조금씩 달라지는 게(어미, 조사,
    "~에 저장한다" vs "~에 적재한다") 실측으로 확인됐습니다. 정확
    일치만 보면 이런 경우가 중복 제거를 통과하지 못하고 그대로
    쌓입니다.

    단, 정확 일치가 아닌 유사도 판정은 앞머리 주어가 같을 때만
    인정합니다(_same_leading_subject 참고) — 주어만 다르고 나머지 문장이
    비슷한 경우까지 중복으로 묶으면 안 되기 때문입니다.
    """
    if not key:
        return False

    for existing in seen_keys:
        if key == existing:
            return True

        if not _same_leading_subject(key, existing):
            continue

        if (
            difflib.SequenceMatcher(None, key, existing).ratio()
            >= _SIMILARITY_THRESHOLD
        ):
            return True

    return False


def _merge_unique(existing: list[dict], new_items, key_fields) -> None:
    """
    new_items를 existing(딕셔너리 리스트)에 중복 없이 이어 붙입니다.

    key_fields로 지정한 필드 값을 정규화해 비교합니다. 같은 내용이
    다른 청크에서 다시 언급되거나(문단이 두 청크 경계에 걸쳐 반복되는
    경우), 한 청크 안에서 모델이 같은 내용을 두 번 낸 경우를 모두
    잡습니다.
    """
    seen: list[str] = [
        _dedupe_key(*(item.get(field, "") for field in key_fields))
        for item in existing
    ]

    for raw in new_items:
        item = raw.model_dump() if hasattr(raw, "model_dump") else dict(raw)
        key = _dedupe_key(*(item.get(field, "") for field in key_fields))

        if _is_duplicate(key, seen):
            continue

        seen.append(key)
        existing.append(item)


def _merge_extractions(
    results: list[MeetingExtraction],
    overview: MeetingExtraction,
) -> dict:
    """
    구조화 결과를 하나로 합칩니다.

    project·users는 overview(전체 원문 통짜 호출) 결과만 씁니다 — 청크
    여러 개에서 합치면 청크마다 다른 국소 주제가 project.goals/users에
    하나씩 얹혀 서로 무관한 내용이 뒤섞입니다(실측 확인됨). "회의 전체가
    무엇에 관한 것인가"는 전체를 한 번은 봐야 답할 수 있습니다.

    requirements·scenarios·decisions·constraints는 results(청크별 결과)만
    합칩니다. overview는 넣지 않습니다 — overview는 같은 사실을 청크들과
    다른 표현으로 다시 서술하는데, 표현이 얼마나 다를지 예측할 수 없어
    유사도 dedup도 항상 잡는다는 보장이 없습니다. 아예 합치는 대상에서
    빼는 편이 안전합니다.

    requirements는 functional/non_functional/data/technical 네 분류를
    통틀어 하나의 중복 판정 집합을 씁니다. 같은 내용이 서로 다른
    분류에 중복 등록되는 문제가 실행 결과로 확인됐으므로, 같은 내용이면
    먼저 나온 분류(REQUIREMENT_CATEGORIES 순서, functional 우선)를
    유지하고 나머지는 버립니다.
    """
    if not results:
        raise ValueError("병합할 구조화 결과가 없습니다.")

    merged: dict = {
        "project": overview.project.model_dump(),
        "users": [item.model_dump() for item in overview.users],
        "requirements": {category: [] for category in REQUIREMENT_CATEGORIES},
        "scenarios": [],
        "decisions": [],
        "constraints": [],
        "unresolved": [],
    }

    requirement_seen: list[str] = []

    for result in results:
        _merge_unique(
            merged["scenarios"],
            result.scenarios,
            ["actor", "trigger", "result"],
        )
        _merge_unique(merged["decisions"], result.decisions, ["content"])
        _merge_unique(
            merged["constraints"],
            result.constraints,
            ["type", "content"],
        )

        for category in REQUIREMENT_CATEGORIES:
            for raw_item in getattr(result.requirements, category):
                item = raw_item.model_dump()
                key = _dedupe_key(item.get("content", ""))

                if _is_duplicate(key, requirement_seen):
                    continue

                requirement_seen.append(key)
                merged["requirements"][category].append(item)

        for note in result.unresolved:
            if note not in merged["unresolved"]:
                merged["unresolved"].append(note)

    return merged


def _extract_structured(
    client,
    relevant_text: str,
    glossary_text: str,
) -> dict:
    """
    CHUNK_TRIGGER_CHARS 이하는 단일 호출로 끝냅니다(09-15에 확인된
    "정리된 문서" 품질을 그대로 유지). 그보다 길면 project·users는
    전체 원문 통짜 호출로, 나머지(requirements·scenarios·decisions·
    constraints)는 청크별 호출로 뽑아 병합합니다. 둘 다 STRONG_MODEL을
    씁니다.

    긴 회의록은 "전체 원문 1회 + 청크별 N회"로 총 N+1번 호출합니다.
    """
    system_prompt = build_system_prompt(glossary_text)

    def call(text: str) -> MeetingExtraction:
        return client.chat.completions.create(
            **build_chat_kwargs(
                model=STRONG_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    *build_messages(text),
                ],
                response_model=MeetingExtraction,
                max_tokens=STRONG_MODEL_MAX_TOKENS,
                max_retries=MAX_RETRIES,
                temperature=TEMPERATURE,
            )
        )

    if len(relevant_text) <= CHUNK_TRIGGER_CHARS:
        return call(relevant_text).model_dump()

    chunks = chunk_meeting_text(relevant_text)

    if len(chunks) <= 1:
        result = call(relevant_text)
        return _merge_extractions([result], overview=result)

    logger.info(
        "노드 1 구조화 호출 %s건(청크)+1건(전체 원문)으로 분할 "
        "(관련 원문 %s자 > 임계값 %s자, STRONG_MODEL=%s).",
        len(chunks),
        len(relevant_text),
        CHUNK_TRIGGER_CHARS,
        STRONG_MODEL,
    )

    # N+1번 호출을 순서대로 부르면 호출 하나(약 100~140초, 실측)가
    # 쌓여서 긴 회의록은 20분 넘게 걸립니다 — 동기 API 응답을 기다리는
    # 사용자에게는 못 쓰는 수준입니다. 서로 독립된 호출(청크끼리, 청크와
    # 전체 원문 통짜 호출)이라 병렬로 부를 수 있습니다. I/O 대기가
    # 대부분이라 스레드로 충분합니다.
    with ThreadPoolExecutor(max_workers=min(len(chunks) + 1, 8)) as executor:
        overview_future = executor.submit(call, relevant_text)
        chunk_futures = [executor.submit(call, chunk) for chunk in chunks]

        overview = overview_future.result()
        chunk_results = [future.result() for future in chunk_futures]

    return _merge_extractions(chunk_results, overview=overview)


@dataclass
class NodeResult:
    """노드 출력과 품질 검증 결과."""

    data: dict
    evidence: EvidenceReport = None
    notes: list[str] = field(default_factory=list)


@traceable(name="meeting_analysis.run")
def run(
    meeting_text: str,
    meeting_id: str,
    glossary_text: str = "",
    on_stage=None,
) -> NodeResult:
    """
    회의록의 개발 관련성을 판별하고 관련 내용만 구조화합니다.

    glossary_text는 선택값입니다.
    용어집이 없거나 빈 문자열이어도 정상적으로 실행됩니다.

    on_stage: 있으면 각 내부 단계 시작 시 사람이 읽을 라벨(str)로 호출합니다
    (선택, develop 2026-09-15 — "회의록 분석 중…" 하나로 뭉뚱그려져 있어
    실측 ~100초 동안 진행 상황이 안 바뀌어 보인다는 요청으로 내부 단계별로
    세분화했습니다).

    관련성 판별(assess_meeting)은 MODEL(기본 gpt-4o)로 충분해 그대로 두고,
    실제 구조화 추출만 STRONG_MODEL(기본 gpt-5)을 씁니다 — 긴 회의록에서
    여러 화제가 섞여 있을 때 프로젝트 범위를 종합적으로 판단하는 게
    MODEL로는 매번 좁게 쏠리는 현상이 실측됐고(shared/retry_config.py의
    STRONG_MODEL 주석 참고), 추론 계열 모델로 바꾸니 훨씬 넓고 완전한
    결과가 나왔습니다. 관련 원문이 CHUNK_TRIGGER_CHARS를 넘으면 청크
    분할+병합으로 전환합니다(위 모듈 docstring, _extract_structured 참고).
    """

    def _stage(label: str) -> None:
        if on_stage:
            on_stage(label)

    try:
        if not meeting_text.strip():
            raise MeetingEligibilityError(
                "회의록 내용이 비어 있습니다. 회의 내용을 입력해 주세요.",
                cause_code="MEETING_NEEDS_CLARIFICATION",
            )

        _stage("회의록 구조화 중…")

        eligibility, relevant_text = assess_meeting(
            client=get_client(MODEL),
            meeting_text=meeting_text,
            glossary_text=glossary_text,
            model=MODEL,
            max_retries=MAX_RETRIES,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )

        structured_fields = _extract_structured(
            client=get_client(STRONG_MODEL),
            relevant_text=relevant_text,
            glossary_text=glossary_text,
        )

    except MeetingEligibilityError as error:
        raise NodeGenerationError(
            str(error),
            cause_code=error.cause_code,
            node="meeting_analysis",
            original=error,
        ) from error

    except InstructorRetryException as error:
        attempt_count = getattr(
            error,
            "n_attempts",
            MAX_RETRIES + 1,
        )

        logger.exception(
            (
                "노드 1 회의록 구조화 실패. "
                "재시도 %s회를 모두 사용했습니다. "
                "meeting_id=%s"
            ),
            attempt_count,
            meeting_id,
        )

        raise NodeGenerationError(
            (
                "AI가 회의록을 정해진 형식으로 구조화하지 못했습니다. "
                f"총 {attempt_count}회의 시도를 완료했습니다. "
                "회의록 내용이 너무 짧거나 모호하지 않은지 확인해 주세요."
            ),
            cause_code="LLM_RETRY_EXHAUSTED",
            node="meeting_analysis",
            original=error,
        ) from error

    except RuntimeError as error:
        logger.exception(
            "노드 1 회의록 구조화 설정 오류. meeting_id=%s",
            meeting_id,
        )

        raise NodeGenerationError(
            (
                "AI 서비스 설정에 문제가 있어 회의록을 분석할 수 없습니다. "
                "관리자에게 문의해 주세요."
            ),
            cause_code="CONFIG_ERROR",
            node="meeting_analysis",
            original=error,
        ) from error

    except APIError as error:
        logger.exception(
            "노드 1 OpenAI API 호출 오류. meeting_id=%s",
            meeting_id,
        )

        raise NodeGenerationError(
            (
                "AI 서비스 호출에 실패했습니다. "
                "잠시 후 다시 시도해 주세요."
            ),
            cause_code="LLM_API_ERROR",
            node="meeting_analysis",
            original=error,
        ) from error

    except Exception as error:
        logger.exception(
            (
                "노드 1 회의록 구조화 중 "
                "예상하지 못한 오류. meeting_id=%s"
            ),
            meeting_id,
        )

        raise NodeGenerationError(
            "회의록 분석 중 예상하지 못한 오류가 발생했습니다.",
            cause_code="UNKNOWN",
            node="meeting_analysis",
            original=error,
        ) from error

    data = MeetingStructured(
        meeting_id=meeting_id,
        **structured_fields,
    ).model_dump(mode="json")

    # ── [2] Evidence 검증 — 표시만, 삭제 안 함 ───────────────
    _stage("근거자료 검증 중…")
    evidence_report = verify_and_mark(
        data,
        relevant_text,
    )

    # ── [3] 교차 규칙 검증 ───────────────────────────────────
    _stage("정합성 검사 중…")
    validation_notes = cross_rules.check(data)

    # ── [4] 커버리지 보완 진단 — 회의록 길이·청크 개수와 무관하게 1회 ──
    # 추출 결과가 실행마다 달라지는 문제(recall variance)를 프롬프트로는
    # 완전히 없앨 수 없어, 놓친 게 있을 수 있다는 신호만 추가로 남긴다.
    # 실패해도 이 결과에 영향을 주지 않는다(coverage_check.check_coverage
    # 참고).
    _stage("커버리지 확인 중…")
    coverage_gaps = check_coverage(
        client=get_client(MODEL),
        relevant_text=relevant_text,
        data=data,
        model=MODEL,
        max_retries=MAX_RETRIES,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
    )
    validation_notes = validation_notes + [
        (
            "커버리지 확인 필요 — 다음 원문 내용이 추출 결과에 "
            f"반영되지 않았을 수 있습니다: {gap}"
        )
        for gap in coverage_gaps
    ]
    data["validation_notes"] = validation_notes

    logger.info(
        (
            "회의록 구조화 완료. meeting_id=%s, "
            "eligibility=%s, evidence_pass_rate=%.2f"
        ),
        meeting_id,
        eligibility.status,
        evidence_report.pass_rate,
    )

    return NodeResult(
        data=data,
        evidence=evidence_report,
        notes=validation_notes,
    )


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    meeting_path = Path(
        sys.argv[1]
        if len(sys.argv) > 1
        else "tests/fixtures/meeting_note_1_complete.md"
    )

    glossary_path = (
        Path(sys.argv[2])
        if len(sys.argv) > 2
        else None
    )

    glossary_text = (
        glossary_path.read_text(encoding="utf-8")
        if glossary_path
        else ""
    )

    result = run(
        meeting_text=meeting_path.read_text(encoding="utf-8"),
        meeting_id=meeting_path.stem,
        glossary_text=glossary_text,
    )

    output_directory = Path("out")
    output_directory.mkdir(exist_ok=True)

    output_path = (
        output_directory
        / f"{meeting_path.stem}.json"
    )

    output_path.write_text(
        json.dumps(
            result.data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 64)
    print(f"입력: {meeting_path}")
    print(f"출력: {output_path}")
    print("-" * 64)
    print(format_report(result.evidence))

    unresolved = result.data.get(
        "unresolved",
        [],
    )

    if unresolved:
        print()
        print(f"미해결 항목: {len(unresolved)}건")

        for item in unresolved:
            print(f"  {item}")

    if result.notes:
        print()
        print("교차 규칙 검증 결과")

        for note in result.notes:
            print(f"  {note}")

    requirements = result.data["requirements"]

    print()
    print("추출 건수")

    for category in [
        "functional",
        "non_functional",
        "data",
        "technical",
    ]:
        count = len(requirements[category])
        print(
            f"  requirements.{category}: {count}"
        )

    for category in [
        "users",
        "scenarios",
        "decisions",
        "constraints",
    ]:
        count = len(result.data[category])
        print(f"  {category}: {count}")

    print("=" * 64)

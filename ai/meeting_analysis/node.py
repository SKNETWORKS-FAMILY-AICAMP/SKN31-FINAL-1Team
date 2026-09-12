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
"""

import logging
from dataclasses import dataclass, field

from openai import APIError

try:
    from instructor.core import InstructorRetryException
except ImportError:
    from instructor.exceptions import InstructorRetryException

from shared.errors import NodeGenerationError
from shared.llm_client import build_chat_kwargs, get_client
from shared.retry_config import (
    MAX_RETRIES,
    MAX_TOKENS,
    MODEL,
    TEMPERATURE,
)

from .eligibility import (
    MeetingEligibilityError,
    assess_meeting,
)
from .prompts import (
    SYSTEM_PROMPT,
    build_messages,
)
from .schemas import (
    MeetingExtraction,
    MeetingStructured,
)
from .validators import cross_rules
from .validators.evidence import (
    EvidenceReport,
    format_report,
    verify_and_mark,
)


logger = logging.getLogger(__name__)


@dataclass
class NodeResult:
    """노드 출력과 품질 검증 결과."""

    data: dict
    evidence: EvidenceReport = None
    notes: list[str] = field(default_factory=list)


def run(
    meeting_text: str,
    meeting_id: str,
    glossary_text: str = "",
) -> NodeResult:
    """
    회의록의 개발 관련성을 판별하고 관련 내용만 구조화합니다.

    glossary_text는 선택값입니다.
    용어집이 없거나 빈 문자열이어도 정상적으로 실행됩니다.
    """

    try:
        if not meeting_text.strip():
            raise MeetingEligibilityError(
                "회의록 내용이 비어 있습니다. 회의 내용을 입력해 주세요.",
                cause_code="MEETING_NEEDS_CLARIFICATION",
            )

        client = get_client(MODEL)

        eligibility, relevant_text = assess_meeting(
            client=client,
            meeting_text=meeting_text,
            glossary_text=glossary_text,
            model=MODEL,
            max_retries=MAX_RETRIES,
            temperature=TEMPERATURE,
        )

                # 임시 진단: 관련성 판별 과정에서 핵심 정보가 사라졌는지 확인합니다.
        check_terms = [
            "리테일링크",
            "사전 사용자 인터뷰",
            "11명",
            "품절",
            "과재고",
            "사장이 매장을 비운",
        ]

        print(
            "\n[입력 진단] 전체 회의록 길이:",
            len(meeting_text),
            "| 선별된 회의록 길이:",
            len(relevant_text),
            flush=True,
        )

        for term in check_terms:
            print(
                f"[입력 진단] {term!r}",
                f"| 전체 입력: {term in meeting_text}",
                f"| 선별 입력: {term in relevant_text}",
                flush=True,
            )

        messages = build_messages(relevant_text)

        extraction = client.chat.completions.create(
            **build_chat_kwargs(
                model=MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    *messages,
                ],
                response_model=MeetingExtraction,
                max_tokens=MAX_TOKENS,
                max_retries=MAX_RETRIES,
                temperature=TEMPERATURE,
            )
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
        **extraction.model_dump(),
    ).model_dump(mode="json")

    evidence_report = verify_and_mark(
        data,
        relevant_text,
    )

    validation_notes = cross_rules.check(data)
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
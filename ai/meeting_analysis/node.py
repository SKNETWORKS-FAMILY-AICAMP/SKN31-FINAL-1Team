"""
노드 1 회의록 구조화 — 실행.

검증 순서:
  [1] 스키마 검증        Instructor가 처리 (재시도 포함)
  [2] Evidence 원문 검증  코드 — 항목에 evidence_status 부여, 삭제 안 함
  [3] 교차 규칙 검증      코드

[1] 이후로는 LLM을 부르지 않으므로 같은 입력에 항상 같은 결과가 나옵니다.

※ 기존의 [3] 항목 처리(삭제) 단계가 사라졌습니다.
  보존 방식으로 바뀌면서 verify_and_mark()가 검사와 표시를 함께 합니다.

실패 처리:
  Instructor가 재시도(초기 시도 + MAX_RETRIES회)를 모두 소진하면
  InstructorRetryException을 던진다. 이걸 그대로 위로 흘려보내면
  호출부가 원인을 알 수 없는 채로 뭉뚱그려 처리하게 되므로, 여기서
  로그를 남기고 원인별로 구분된 NodeGenerationError로 다시 던진다.
  (호출부가 cause_code별로 다른 안내문을 고르는 부분은 별도 작업 —
  shared/errors.py 참고.)
"""

import logging
from dataclasses import dataclass, field

from openai import APIError

try:
    from instructor.core import InstructorRetryException
except ImportError:  # 구버전 instructor 호환
    from instructor.exceptions import InstructorRetryException

from shared.errors import NodeGenerationError
from shared.llm_client import build_chat_kwargs, get_client
from shared.retry_config import MAX_RETRIES, MAX_TOKENS, MODEL, TEMPERATURE

from .prompts import SYSTEM_PROMPT, build_messages
from .schemas import MeetingExtraction, MeetingStructured
from .validators import cross_rules
from .validators.evidence import EvidenceReport, format_report, verify_and_mark

logger = logging.getLogger(__name__)


@dataclass
class NodeResult:
    """노드 출력 + 품질 지표. graph.py에서 State로 옮겨 담습니다."""

    data: dict
    evidence: EvidenceReport = None
    notes: list[str] = field(default_factory=list)


def run(meeting_text: str, meeting_id: str) -> NodeResult:
    # ── [1] AI 구조화 + 스키마 검증 ──────────────────────────
    # Instructor가 JSON 파싱 · Pydantic 검증 · 실패 시 재호출까지 처리합니다.
    try:
        client = get_client()
        messages = build_messages(meeting_text)

        extraction = client.chat.completions.create(
            **build_chat_kwargs(
                model=MODEL,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
                response_model=MeetingExtraction,
                max_tokens=MAX_TOKENS,
                max_retries=MAX_RETRIES,
                temperature=TEMPERATURE,
            )
        )
    except InstructorRetryException as e:
        logger.exception(
            "노드① 회의록 구조화 실패 — 재시도 %s회 모두 스키마 검증 실패 "
            "(meeting_id: %s)",
            e.n_attempts, meeting_id,
        )
        raise NodeGenerationError(
            "AI가 회의록을 정해진 형식으로 구조화하지 못했습니다"
            f"(재시도 {e.n_attempts}회 모두 실패). "
            "회의록 내용이 너무 짧거나 모호하지 않은지 확인해 주세요.",
            cause_code="LLM_RETRY_EXHAUSTED",
            node="meeting_analysis",
            original=e,
        ) from e
    except RuntimeError as e:
        # get_client()가 OPENAI_API_KEY 미설정 시 던지는 예외.
        logger.exception(
            "노드① 회의록 구조화 실패 — 설정 오류 (meeting_id: %s)", meeting_id,
        )
        raise NodeGenerationError(
            "AI 서비스 설정에 문제가 있어 회의록을 분석할 수 없습니다. "
            "관리자에게 문의해 주세요.",
            cause_code="CONFIG_ERROR",
            node="meeting_analysis",
            original=e,
        ) from e
    except APIError as e:
        logger.exception(
            "노드① 회의록 구조화 실패 — OpenAI API 호출 오류 (meeting_id: %s)",
            meeting_id,
        )
        raise NodeGenerationError(
            "AI 서비스 호출에 실패했습니다(네트워크 또는 서비스 오류). "
            "잠시 후 다시 시도해 주세요.",
            cause_code="LLM_API_ERROR",
            node="meeting_analysis",
            original=e,
        ) from e
    except Exception as e:
        logger.exception(
            "노드① 회의록 구조화 실패 — 알 수 없는 오류 (meeting_id: %s)",
            meeting_id,
        )
        raise NodeGenerationError(
            "회의록 분석 중 예상치 못한 오류가 발생했습니다.",
            cause_code="UNKNOWN",
            node="meeting_analysis",
            original=e,
        ) from e

    data = MeetingStructured(
        meeting_id=meeting_id, **extraction.model_dump()
    ).model_dump(mode="json")

    # ── [2] Evidence 검증 — 표시만, 삭제 안 함 ───────────────
    report = verify_and_mark(data, meeting_text)

    # ── [3] 교차 규칙 검증 ───────────────────────────────────
    notes = cross_rules.check(data)
    data["validation_notes"] = notes

    return NodeResult(data=data, evidence=report, notes=notes)


# ─────────────────────────────────────────────────────────────
# 개발 중 단독 실행.
#     python -m meeting_analysis.node tests/fixtures/meeting_note_1_complete.md
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    path = Path(sys.argv[1] if len(sys.argv) > 1
                else "tests/fixtures/meeting_note_1_complete.md")
    result = run(path.read_text(encoding="utf-8"), path.stem)

    out = Path("out")
    out.mkdir(exist_ok=True)
    out_path = out / f"{path.stem}.json"
    out_path.write_text(
        json.dumps(result.data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("=" * 64)
    print(f"입력: {path}")
    print(f"출력: {out_path}")
    print("-" * 64)
    print(format_report(result.evidence))

    if result.data.get("unresolved"):
        print(f"\n[unresolved] {len(result.data['unresolved'])}건 "
              "— 회의에서 논의되지 않은 항목")
        for u in result.data["unresolved"]:
            print(f"  · {u}")

    if result.notes:
        print("\n[교차 규칙 위반]")
        for n in result.notes:
            print(f"  · {n}")

    reqs = result.data["requirements"]
    print("\n[추출 건수]")
    for k in ["functional", "non_functional", "data", "technical"]:
        print(f"  requirements.{k:15}: {len(reqs[k])}")
    for k in ["users", "scenarios", "decisions", "constraints"]:
        print(f"  {k:28}: {len(result.data[k])}")

    # decisions 분류별 집계 — feature/tech/scope가 골고루 나오는지 확인
    from collections import Counter
    cats = Counter(d["category"] for d in result.data["decisions"])
    if cats:
        print("\n[decisions 분류]")
        for c, n in cats.items():
            print(f"  {c:28}: {n}")

    print("=" * 64)

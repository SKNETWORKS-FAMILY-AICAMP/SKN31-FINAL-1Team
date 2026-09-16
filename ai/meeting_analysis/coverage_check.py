"""
노드① 회수율 보완 진단 — 요약 대조 커버리지 체크.

## 왜 필요한가

같은 모델·같은 입력·temperature=0으로 반복 실행해도 추출 결과가
크게 달라지는 걸 실측으로 확인했다(예: 목표 1건 vs 7건, 같은
4,865자 회의록에서). 청크 병합에서도 특정 주제가 통째로 빠지는
사례를 실측했다(29,372자 회의록에서 후반부 절반이 한 번은 통째로
누락). 프롬프트를 더 정교하게 다듬는 것만으로는 이 변동성 자체를
없앨 수 없다 — gpt-5(STRONG_MODEL)의 근본적인 특성이다.

## 무엇을 하는가

추출이 끝난 뒤, 이미 뽑힌 내용의 짧은 요약과 번호를 매긴 원문을
모델에게 다시 보여주고 "요약에 전혀 반영되지 않은 문단이 있는가"만
묻는다. 문단 번호만 받으므로(eligibility.py의 mixed 2단계와 같은
이유) 출력이 회의록 길이와 무관하게 짧다.

찾은 문단을 다시 추출해 구조화 항목으로 만들지 않는다 — 이 호출의
역할은 "놓친 게 있을 수 있다"는 신호를 남기는 것뿐이다. 신호를 보고
실제로 채울지는 PM의 판단이다(node.py가 validation_notes에 남겨
화면에 노출한다).

애매하면 포함하는 eligibility.py의 mixed 판정과 반대로, 여기서는
애매하면 포함하지 않는다. 여기서 뭔가를 포함하면(오탐) PM이 이미
반영된 내용을 다시 확인하느라 시간을 쓰고, 빠뜨리면(누락) 원래
있던 변동성 문제로 그대로 남을 뿐이라 새로운 손실이 아니다.
비대칭적인 실패 비용이 반대이므로 지시도 반대다.

## 예산과 실패 처리

노드①마다 정확히 1회 호출한다(회의록 길이·청크 개수와 무관, MODEL
등급 사용 — STRONG_MODEL만큼 느리고 비쌀 필요가 없다). 이 호출이
실패해도 노드①의 다른 결과에는 영향을 주지 않는다 — 본 추출이 아니라
보조 확인이므로, 이 호출 하나가 전체 파이프라인의 새 장애점이 되면
안 된다(실패 시 로그만 남기고 빈 결과로 계속 진행).
"""

import logging

from pydantic import BaseModel, Field

from shared.llm_client import build_chat_kwargs

from .eligibility_prompt import number_paragraphs

logger = logging.getLogger(__name__)


COVERAGE_SYSTEM_PROMPT = """이미 구조화된 요약과 번호가 매겨진 회의록 원문을 비교하는
작업입니다.

요약에 전혀 반영되지 않은, 개발 기획에 필요한 내용을 담은 문단이
있으면 그 번호만 배열로 반환합니다.

주의:
- 요약과 표현만 다를 뿐 같은 내용을 가리키면 포함하지 않습니다.
- 인사말, 잡담, 이미 요약에 있는 내용의 반복은 포함하지 않습니다.
- 이건 다시 추출하는 단계가 아니라 놓친 게 있는지 확인하는 보조
  점검입니다. 애매하면 포함하지 않습니다 — 확실히 빠진 것만 고릅니다.

문단 내용을 다시 쓰지 말고 번호만 반환합니다."""


class CoverageGaps(BaseModel):
    """요약에 반영되지 않은 것으로 보이는 원문 문단 번호."""

    paragraph_numbers: list[int] = Field(default_factory=list)


def _summarize(data: dict) -> list[str]:
    """이미 추출된 항목의 content만 짧게 모읍니다(근거 문장은 제외)."""
    lines: list[str] = []

    project = data.get("project") or {}
    if project.get("problem"):
        lines.append(str(project["problem"]))
    for item in project.get("problem_items") or []:
        lines.append(str(item.get("content", "")))
    for item in project.get("goals") or []:
        lines.append(str(item.get("content", "")))

    requirements = data.get("requirements") or {}
    if isinstance(requirements, dict):
        for category_items in requirements.values():
            for item in category_items or []:
                if isinstance(item, dict):
                    lines.append(str(item.get("content", "")))

    for decision in data.get("decisions") or []:
        lines.append(str(decision.get("content", "")))

    for constraint in data.get("constraints") or []:
        lines.append(str(constraint.get("content", "")))

    for note in data.get("unresolved") or []:
        lines.append(str(note))

    return [line.strip() for line in lines if line and line.strip()]


def build_messages(
    relevant_text: str,
    data: dict,
) -> tuple[list[dict], list[tuple[int, str]]]:
    """커버리지 확인 메시지와, 답을 되돌릴 때 쓸 번호-원문 매핑을 만든다."""
    numbered = number_paragraphs(relevant_text)
    body = "\n".join(f"[{n}] {t}" for n, t in numbered)
    summary = (
        "\n".join(f"- {line}" for line in _summarize(data))
        or "(추출된 내용 없음)"
    )

    messages = [
        {"role": "system", "content": COVERAGE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"[이미 추출된 요약]\n{summary}\n\n"
                f"[번호가 매겨진 회의록 원문]\n{body}"
            ),
        },
    ]

    return messages, numbered


def check_coverage(
    client,
    relevant_text: str,
    data: dict,
    *,
    model: str,
    max_retries: int,
    temperature,
    max_tokens: int,
) -> list[str]:
    """
    놓쳤을 수 있는 원문 문단을 찾아 반환한다. 실패하면 빈 배열을
    반환한다 — 보조 확인 실패가 노드①의 나머지 결과를 막을 이유는 없다.
    """
    if not relevant_text.strip():
        return []

    try:
        messages, numbered = build_messages(relevant_text, data)
        by_number = dict(numbered)

        result = client.chat.completions.create(
            **build_chat_kwargs(
                model=model,
                messages=messages,
                response_model=CoverageGaps,
                max_tokens=max_tokens,
                max_retries=max_retries,
                temperature=temperature,
            )
        )

        return [
            by_number[n]
            for n in sorted(set(result.paragraph_numbers))
            if n in by_number
        ]

    except Exception:
        logger.exception("커버리지 보조 확인 호출 실패 — 건너뜁니다.")
        return []

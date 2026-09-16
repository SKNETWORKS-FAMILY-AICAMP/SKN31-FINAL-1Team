"""
노드 1 긴 회의록 분할.

## 문제

정리되지 않은 녹취록을 gpt-5(STRONG_MODEL) 단일 호출로 돌려도, 주제가
많고 긴 회의록에서는 특정 주제 하나가 통째로 빠지는 경우가 실측으로
확인됐습니다. gpt-4o보다 훨씬 낫지만 100%는 아닙니다 — 회의 전체를 한
호출에 다 담으려다 보니 특정 주제(예: 이미지 스타일 분류 모델 관련
논의)에 대한 발언들이 서로 떨어져 있으면 모델이 그걸 하나로 묶어
"요약"하려다 원문과 정확히 일치하지 않는 인용을 만들거나, 아예
언급을 누락합니다.

## 해결

회의록을 문단 단위 청크로 나눠 각각 따로 구조화 호출을 합니다. 청크
하나(약 3,000자)는 회의 전체보다 훨씬 좁은 범위라, 그 안에 있는 발언은
모델이 떨어뜨리지 않고 그대로 인용하기 쉽습니다(멀리 떨어진 문장을
합칠 필요가 없음). 여러 청크에서 나온 결과를 병합하면 회의 전체에
흩어진 내용을 놓칠 확률이 줄어듭니다.

project·users는 이 청크 분할과 별개로 전체 원문 통짜 호출 하나로만
뽑습니다(node.py의 _extract_structured 참고) — "회의 전체가 무엇에
관한 것인가"는 청크 하나로는 답할 수 없는 질문이기 때문입니다.

짧은 회의록은 문단을 다 합쳐도 CHUNK_MAX_CHARS를 넘지 않아 청크가
하나만 나옵니다 — 그 경우 청크 호출과 project 전용 호출이 사실상
같은 내용을 중복 호출하게 되므로, node.py가 이를 감지해 청크 호출을
생략합니다.
"""

import re

# 문장 경계를 잡는 데 쓰는 패턴. 정리된 회의록 기준으로 흔한
# 종결 어미(-다/-요) 뒤 공백, 또는 마침표/물음표/느낌표 뒤 공백을 씁니다.
#
# 2026-09-16: 줄바꿈이 거의 없는 원본 STT 전사본이 들어오면
# split_into_paragraphs가 문단을 한 줄바꿈 단위로도 나누지 못해
# 회의록 전체가 "문단 하나"가 됩니다. 그 문단을 자르지 않고 그대로
# 청크 하나로 두면(_split_long_paragraph를 만들기 전 동작) 청크
# 분할의 원래 목적(모델이 한 호출에서 너무 많은 내용을 다루다 특정
# 주제를 통째로 놓치는 문제)이 그대로 재현됩니다. 문장 경계에서
# 강제로 나눠 이 경우에도 청크가 실제로 여러 개 생기게 합니다.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?다요])\s+")

# 청크 하나의 목표 최대 길이(자).
#
# gpt-4o 기준 실측 비교(6000자=3청크 vs 3000자=6청크)에서 3000자가
# 뚜렷하게 나았습니다(functional 4→11건, technical 1→6건). gpt-5도
# 같은 이유(청크가 작을수록 떨어진 문장을 합칠 필요가 줄어듦)로 같은
# 값을 그대로 씁니다.
CHUNK_MAX_CHARS = 3000


def split_into_paragraphs(text: str) -> list[str]:
    """빈 줄과 줄바꿈을 경계로 문단을 나눕니다."""
    return [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n|\n", text)
        if paragraph.strip()
    ]


def _split_long_paragraph(paragraph: str, max_chars: int) -> list[str]:
    """줄바꿈이 없어 max_chars를 넘는 문단 하나를 문장 단위로 강제 분할합니다.

    문장 경계(_SENTENCE_BOUNDARY)를 우선 쓰고, 그마저 하나도 없으면
    (문장부호와 종결 어미가 전혀 없는 극단적인 경우) 공백 단위로
    나눕니다. 단어 중간은 자르지 않습니다 — 근거 인용이 단어를
    반으로 쪼갠 채 남으면 원문 대조가 아예 불가능해지기 때문입니다.
    """
    pieces = [piece for piece in _SENTENCE_BOUNDARY.split(paragraph) if piece]

    if len(pieces) <= 1:
        pieces = [word for word in paragraph.split(" ") if word]

    if len(pieces) <= 1:
        return [paragraph]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for piece in pieces:
        if current and current_len + len(piece) + 1 > max_chars:
            chunks.append(" ".join(current))
            current, current_len = [], 0

        current.append(piece)
        current_len += len(piece) + 1

    if current:
        chunks.append(" ".join(current))

    return chunks


def chunk_meeting_text(
    text: str,
    max_chars: int = CHUNK_MAX_CHARS,
) -> list[str]:
    """
    문단 경계를 지키며 회의록을 max_chars 이하 묶음으로 나눕니다.

    문단 하나가 max_chars보다 길면(드묾) 문장 경계에서 추가로
    나눕니다(_split_long_paragraph). 문장 경계도 없는 극단적인
    경우에만 공백 단위로 나누고, 그마저 없으면 문단을 그대로 둡니다.
    문단을 통째로 두지 않는 이유는 줄바꿈이 거의 없는 원본 STT
    전사본이 들어오면 회의록 전체가 문단 하나가 되어, 청크 분할이
    사실상 무력화되기 때문입니다(_SENTENCE_BOUNDARY 주석 참고).

    반환되는 청크는 원문 순서를 유지합니다. 회의 흐름이 뒤섞이면
    한 청크만 보고 판단하는 구조화 단계가 배경과 결정의 선후를
    잘못 읽습니다.
    """
    paragraphs = split_into_paragraphs(text)

    if not paragraphs:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append("\n\n".join(current))
                current, current_len = [], 0
            chunks.extend(_split_long_paragraph(paragraph, max_chars))
            continue

        if current and current_len + len(paragraph) + 2 > max_chars:
            chunks.append("\n\n".join(current))
            current, current_len = [], 0

        current.append(paragraph)
        current_len += len(paragraph) + 2

    if current:
        chunks.append("\n\n".join(current))

    return chunks

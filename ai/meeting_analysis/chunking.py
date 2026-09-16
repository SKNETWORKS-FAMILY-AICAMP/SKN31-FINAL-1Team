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


def chunk_meeting_text(
    text: str,
    max_chars: int = CHUNK_MAX_CHARS,
) -> list[str]:
    """
    문단 경계를 지키며 회의록을 max_chars 이하 묶음으로 나눕니다.

    문단 하나가 max_chars보다 길면(드묾) 그 문단 자체를 청크 하나로
    둡니다. 문단 중간을 자르면 그 문단 안의 근거 인용이 청크 경계에
    걸려 원문과 어긋날 수 있기 때문입니다.

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
            chunks.append(paragraph)
            continue

        if current and current_len + len(paragraph) + 2 > max_chars:
            chunks.append("\n\n".join(current))
            current, current_len = [], 0

        current.append(paragraph)
        current_len += len(paragraph) + 2

    if current:
        chunks.append("\n\n".join(current))

    return chunks

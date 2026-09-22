"""
tests/test_eligibility_passages.py

적격성 판정의 근거 대조(validate_relevant_passages) 테스트.

2026-09-14 추가 배경:
지표 측정 중 meeting_note_3_long에서 기획서 생성이 통째로 실패했다.
원인은 발췌문을 커서로 앞에서부터만 찾는 방식이었다 — 모델이 발췌를
원문 순서대로 내놓지 않으면 뒤쪽에서 찾지 못해 판정 전체가 죽었다.

해당 회의록의 발췌는 23건이었다. 건당 순서가 어긋날 확률이 낮아도
23건이 모두 순서대로여야 통과하므로 실패 확률이 누적된다. 실제로
한 번 실패하고 한 번 통과하는, 재현율이 낮은 결함이었다.

LLM을 부르지 않는다 — 판정 결과를 직접 만들어 검증 로직만 확인한다.
"""

import pytest

from meeting_analysis.eligibility import (
    MeetingEligibility,
    MeetingEligibilityError,
    find_unused_passage,
    validate_relevant_passages,
)

TEXT = (
    "첫째 문단은 배경 설명입니다.\n\n"
    "둘째 문단은 기능 논의입니다.\n\n"
    "셋째 문단은 일정 논의입니다."
)


def _result(status, passages):
    return MeetingEligibility(
        status=status, reason="판정 이유", relevant_passages=passages,
    )


# ═══════════════════════════════════════════════════════════
# find_unused_passage — 순서 비의존 + 중복 방지
# ═══════════════════════════════════════════════════════════


def test_원문_순서와_달라도_찾는다():
    """이 테스트가 실패하면 커서 전진 방식으로 되돌아간 것이다."""
    셋째 = find_unused_passage("셋째 문단은 일정 논의입니다.", TEXT, [])
    assert 셋째 is not None

    # 뒤쪽을 먼저 쓴 뒤에도 앞쪽을 찾을 수 있어야 한다.
    첫째 = find_unused_passage("첫째 문단은 배경 설명입니다.", TEXT, [셋째])
    assert 첫째 is not None
    assert 첫째[0] < 셋째[0]


def test_이미_쓴_구간은_다시_쓰지_않는다():
    """중복 방지는 커서의 본래 목적이므로 유지되어야 한다."""
    처음 = find_unused_passage("둘째 문단은 기능 논의입니다.", TEXT, [])
    다시 = find_unused_passage("둘째 문단은 기능 논의입니다.", TEXT, [처음])

    assert 처음 is not None
    assert 다시 is None


def test_같은_문장이_두_번_나오면_두_번째를_찾는다():
    반복 = "같은 문장입니다.\n\n중간 문단.\n\n같은 문장입니다."
    첫 = find_unused_passage("같은 문장입니다.", 반복, [])
    둘 = find_unused_passage("같은 문장입니다.", 반복, [첫])

    assert 첫 is not None and 둘 is not None
    assert 첫 != 둘


def test_공백_차이는_허용한다():
    """모델이 줄바꿈을 공백으로 합쳐 인용하는 경우가 잦다."""
    assert find_unused_passage("첫째  문단은\n배경 설명입니다.", TEXT, []) is not None


def test_원문에_없으면_찾지_못한다():
    assert find_unused_passage("회의록에 없는 문장입니다.", TEXT, []) is None


# ═══════════════════════════════════════════════════════════
# relevant — 발췌를 쓰지 않으므로 중단하지 않는다
# ═══════════════════════════════════════════════════════════


def test_relevant는_대조_실패해도_생성을_중단하지_않는다():
    """
    relevant 경로는 전체 원문을 반환하므로 발췌 결과를 쓰지 않는다.
    쓰이지도 않는 검증 때문에 기획서를 못 만드는 것은 비용이 과하다.
    """
    result = _result("relevant", ["첫째 문단은 배경 설명입니다.", "원문에 없는 문장."])

    반환 = validate_relevant_passages(result=result, meeting_text=TEXT)

    assert 반환 == TEXT
    assert result.unverified_passages == ["원문에 없는 문장."]


def test_relevant는_전부_통과하면_미확인이_비어_있다():
    result = _result("relevant", ["첫째 문단은 배경 설명입니다."])

    validate_relevant_passages(result=result, meeting_text=TEXT)

    assert result.unverified_passages == []


def test_relevant는_발췌_순서가_뒤바뀌어도_통과한다():
    """실패를 일으킨 바로 그 조건이다."""
    result = _result("relevant", [
        "셋째 문단은 일정 논의입니다.",
        "첫째 문단은 배경 설명입니다.",
    ])

    assert validate_relevant_passages(result=result, meeting_text=TEXT) == TEXT
    assert result.unverified_passages == []


# ═══════════════════════════════════════════════════════════
# mixed — 발췌가 곧 하류 입력이므로 검증이 필수
# ═══════════════════════════════════════════════════════════


def test_mixed는_검증된_구간만_원문_순서로_전달한다():
    result = _result("mixed", [
        "셋째 문단은 일정 논의입니다.",
        "첫째 문단은 배경 설명입니다.",
    ])

    반환 = validate_relevant_passages(result=result, meeting_text=TEXT)

    # 발췌 순서가 뒤바뀌어도 전달할 때는 원문 순서로 정렬한다.
    assert 반환.index("첫째") < 반환.index("셋째")
    assert "둘째" not in 반환


def test_mixed는_대조에_실패하면_중단한다():
    """이 경로는 발췌가 하류 입력이므로 못 믿을 근거를 넘길 수 없다."""
    result = _result("mixed", ["첫째 문단은 배경 설명입니다.", "원문에 없는 문장."])

    with pytest.raises(MeetingEligibilityError) as e:
        validate_relevant_passages(result=result, meeting_text=TEXT)

    assert e.value.cause_code == "MEETING_ELIGIBILITY_INVALID"


# ═══════════════════════════════════════════════════════════
# 중단 판정
# ═══════════════════════════════════════════════════════════


@pytest.mark.parametrize("status,code", [
    ("irrelevant", "MEETING_NOT_RELEVANT"),
    ("needs_clarification", "MEETING_NEEDS_CLARIFICATION"),
])
def test_중단_판정은_사유_코드와_함께_예외를_던진다(status, code):
    result = _result(status, [])

    with pytest.raises(MeetingEligibilityError) as e:
        validate_relevant_passages(result=result, meeting_text=TEXT)

    assert e.value.cause_code == code
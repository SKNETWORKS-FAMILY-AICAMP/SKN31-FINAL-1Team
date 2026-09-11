"""
Evidence 검증 단위 테스트 — 보존 방식.

LLM을 부르지 않으므로 빠르고 무료입니다.
정규화 규칙(_PUNCT)을 손볼 때마다 여기서 회귀를 잡으세요.
"""

import pytest

from meeting_analysis.validators.evidence import (
    UNVERIFIED,
    VERIFIED,
    format_report,
    normalize,
    verify_and_mark,
)

MEETING = """박서버: 백엔드는 Django로 간다. 우리 팀이 제일 익숙하다.
정PM: 개발 기간은 8주다. 그 안에 끝내야 한다."""


def _base(**overrides) -> dict:
    data = {
        "meeting_id": "M-TEST",
        "project": {
            "name": "테스트", "background": "b", "problem": "p", "goals": [],
            "background_evidence": {"quote": "개발 기간은 8주다"},
            "problem_evidence": {"quote": "개발 기간은 8주다"},
        },
        "users": [],
        "requirements": {
            "functional": [], "non_functional": [], "data": [], "technical": [],
        },
        "scenarios": [],
        "decisions": [],
        "constraints": [],
        "unresolved": [],
    }
    data.update(overrides)
    return data


def test_정규화는_공백과_문장부호를_제거한다():
    assert normalize("백엔드는 Django로 간다.") == normalize("백엔드는Django로간다")


def test_원문에_있는_인용은_verified():
    data = _base(decisions=[{
        "category": "tech", "content": "백엔드는 Django로 개발한다",
        "evidence": {"quote": "백엔드는 Django로 간다"},
    }])
    report = verify_and_mark(data, MEETING)
    assert data["decisions"][0]["evidence_status"] == VERIFIED
    assert report.unverified == []


def test_원문에_없는_인용은_unverified이고_삭제되지_않는다():
    """보존 방식의 핵심. 항목이 살아 있어야 원인 A/B를 판단할 수 있습니다."""
    data = _base(requirements={
        "functional": [], "data": [], "technical": [],
        "non_functional": [{
            "content": "응답 속도는 3초 이내여야 한다",
            "evidence": {"quote": "빠르게 처리되어야 한다"},   # 원문에 없음
        }],
    })
    report = verify_and_mark(data, MEETING)

    item = data["requirements"]["non_functional"][0]
    assert item["evidence_status"] == UNVERIFIED
    assert item["content"] == "응답 속도는 3초 이내여야 한다"   # 살아 있음
    assert len(report.unverified) == 1
    assert report.unverified[0].path == "requirements.non_functional[0]"


def test_unverified를_unresolved에_넣지_않는다():
    """
    unresolved = 회의에서 논의되지 않음
    unverified = 추출했는데 근거 확인 실패
    두 개는 의미가 달라 섞으면 안 됩니다.
    """
    data = _base(constraints=[{
        "type": "일정", "content": "가짜 제약",
        "evidence": {"quote": "회의록에 없는 문장입니다"},
    }])
    verify_and_mark(data, MEETING)
    assert data["unresolved"] == []


def test_통과율_집계():
    data = _base(constraints=[
        {"type": "일정", "content": "진짜", "evidence": {"quote": "개발 기간은 8주다"}},
        {"type": "기술", "content": "가짜", "evidence": {"quote": "없는문장1입니다"}},
    ])
    report = verify_and_mark(data, MEETING)
    assert report.checked == 4          # project 2(background+problem) + constraints 2
    assert report.verified_count == 3
    assert abs(report.pass_rate - 3 / 4) < 0.01


def test_project의_background와_problem은_evidence가_따로_검증된다():
    """
    2026-09-07 추가.

    예전엔 project.evidence 하나로 background/problem을 같이 대표해서,
    실제로는 goals 쪽 문장이 매칭됐는데 그게 그대로 개요·문제 정의
    두 섹션의 근거로 쓰이는 문제가 있었습니다(리테일링크 기획안에서 발견).
    background_evidence/problem_evidence로 나눈 뒤에는 하나가 틀려도
    다른 하나까지 같이 UNVERIFIED가 되면 안 됩니다 — 서로 독립적이어야 합니다.
    """
    data = _base(project={
        "name": "테스트", "background": "b", "problem": "p", "goals": [],
        "background_evidence": {"quote": "개발 기간은 8주다"},        # 원문에 있음
        "problem_evidence": {"quote": "회의록에 없는 문장입니다"},     # 원문에 없음
    })
    verify_and_mark(data, MEETING)
    project = data["project"]
    assert project["background_evidence_status"] == VERIFIED
    assert project["problem_evidence_status"] == UNVERIFIED


def test_리포트에_quote가_출력된다():
    """원인 A/B를 구분하려면 quote를 눈으로 봐야 합니다."""
    data = _base(constraints=[{
        "type": "기타", "content": "가짜",
        "evidence": {"quote": "없는문장입니다여기"},
    }])
    report = verify_and_mark(data, MEETING)
    assert "없는문장입니다여기" in format_report(report)


@pytest.mark.parametrize("quote,expect_verified", [
    ("백엔드는 Django로 간다", True),      # 정확 일치
    ("백엔드는 Django로 간다.", True),     # 마침표 차이
    ("백엔드는  Django로  간다", True),    # 공백 차이
    ("백엔드는 Django로 갑니다", False),   # 어미 변경 — 경우 B
])
def test_정규화_경계_케이스(quote, expect_verified):
    """
    마지막 케이스가 '경우 B'입니다.
    내용은 맞는데 어미가 달라 매칭이 깨집니다.
    실행 결과에서 이런 게 얼마나 나오는지 보고
    유사도 매칭 도입 여부를 정하세요.
    """
    data = _base(decisions=[{
        "category": "tech", "content": "Django 사용",
        "evidence": {"quote": quote},
    }])
    verify_and_mark(data, MEETING)
    status = data["decisions"][0]["evidence_status"]
    assert (status == VERIFIED) is expect_verified
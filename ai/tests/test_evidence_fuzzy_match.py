"""
노드 ①의 근거 검증기(validators/evidence.py) 유사도 매칭 테스트.

2026-09-16: 완전 일치 매칭만 있을 때, 실제 회의록을 재실행하다 노드①이
원문 "깔끔하게"를 근거 quote에 "깔끗하게"로 한 글자 잘못 옮겨 적어서
내용은 맞게 뽑힌 결정사항 하나가 unverified로 빠지고 하류(plan_draft)
에서 조용히 사라지는 사례를 확인했다. 이 파일은 그 사례를 재현하고,
유사도 매칭이 이를 구제하면서도 진짜 지어낸 근거(할루시네이션)는
여전히 걸러내는지 검증한다.
"""

from meeting_analysis.validators.evidence import (
    UNVERIFIED,
    VERIFIED,
    verify_and_mark,
)


def _structured(quote: str) -> dict:
    return {
        "project": {
            "background": "",
            "background_evidence": {"quote": ""},
            "problem": "",
            "problem_evidence": {"quote": ""},
            "problem_items": [],
            "goals": [],
        },
        "decisions": [
            {
                "category": "scope",
                "content": "프로츠패밀리 데이터는 제외하고 무신사 유즈드를 추가한다",
                "rationale": "",
                "evidence": {"quote": quote},
            }
        ],
    }


def test_한두_글자_오차는_verified로_구제된다():
    """실제로 확인된 사례: '깔끔하게' -> '깔끗하게' 오기."""
    source = (
        "네, 맞는 것 같아요. 차라리 안 하는 걸로 깔끔하게 정리하고 "
        "무신사를 추가하는 방향이 프로젝트하는 데 낫지 않을까요?\n\n"
        "그럴 것 같아요. 프로스펙트리가 아픈 손가락이긴 한데, 데이터를 "
        "받아도 쓸 데가 자꾸 없어요. 무신사 유즈드는 꼭 넣어야 할 것 "
        "같아요."
    )
    quote = (
        "차라리 안 하는 걸로 깔끗하게 정리하고 무신사를 추가하는 방향이 "
        "프로젝트하는 데 낫지 않을까요?\n\n그럴 것 같아요. 프로스펙트리가 "
        "아픈 손가락이긴 한데, 데이터를 받아도 쓸 데가 자꾸 없어요. "
        "무신사 유즈드는 꼭 넣어야 할 것 같아요."
    )

    data = _structured(quote)
    verify_and_mark(data, source)

    assert data["decisions"][0]["evidence_status"] == VERIFIED


def test_완전히_지어낸_근거는_여전히_unverified():
    """할루시네이션(원문에 없는 내용)까지 통과시키면 안 된다."""
    source = (
        "네, 맞는 것 같아요. 차라리 안 하는 걸로 깔끔하게 정리하고 "
        "무신사를 추가하는 방향이 프로젝트하는 데 낫지 않을까요?"
    )
    quote = "이 프로젝트는 내년까지 매출 100억을 목표로 한다."

    data = _structured(quote)
    verify_and_mark(data, source)

    assert data["decisions"][0]["evidence_status"] == UNVERIFIED


def test_원문에_아예_없는_주제도_unverified():
    """원문과 어휘가 거의 겹치지 않는 근거는 구제하지 않는다."""
    source = "저희는 크림과 무신사 유즈드로 중고 데이터를 수집하기로 했습니다."
    quote = "백엔드는 Spring Boot와 MySQL을 사용합니다."

    data = _structured(quote)
    verify_and_mark(data, source)

    assert data["decisions"][0]["evidence_status"] == UNVERIFIED


def test_부정어가_빠진_인용은_verified로_통과하면_안된다():
    """
    2026-09-16: Codex가 재현한 사례의 회귀 테스트. 긴 문장에서 "하지
    않는다"의 부정어만 빼면 문장 길이 대비 편집거리 비중이 작아져
    ratio가 임계값을 넘는데, 뜻은 정반대다. 이런 부정어 뒤집힘은
    유사도가 아무리 높아도 verified로 통과시키면 안 된다.
    """
    source = (
        "이번 프로젝트에서 수집하는 모든 개인정보와 회의록 원문 데이터는 "
        "사내 정책에 따라 암호화되어 저장되며 어떠한 경우에도 외부 서버에 "
        "전송하지 않는다는 원칙을 반드시 지켜야 합니다."
    )
    quote = (
        "이번 프로젝트에서 수집하는 모든 개인정보와 회의록 원문 데이터는 "
        "사내 정책에 따라 암호화되어 저장되며 어떠한 경우에도 외부 서버에 "
        "전송한다는 원칙을 반드시 지켜야 합니다."
    )

    data = _structured(quote)
    verify_and_mark(data, source)

    assert data["decisions"][0]["evidence_status"] == UNVERIFIED

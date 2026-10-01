"""
tests/test_cross_rules.py

교차 규칙 검증(meeting_analysis/validators/cross_rules.py) 테스트.

Pydantic이 못 잡는 필드 간 정합성을 보는 계층이다. 각 필드는 유효한데
조합이 이상한 경우를 찾는다. LLM을 부르지 않고 len()으로 판정하므로
결정적으로 확인할 수 있다.

2026-09-14 추가 배경: 규칙 4개 중 결정 분류 보정 하나만
테스트가 있었다(test_decision_category_repair.py). 나머지 3개와
unresolved 모순 검사는 검증 없이 동작하고 있었다.
"""

from meeting_analysis.validators.cross_rules import (
    MAX_ITEMS_PER_CATEGORY,
    check,
    check_unresolved_consistency,
)


def _req(content, **kw):
    return {"content": content, "evidence": {"quote": content},
            "evidence_status": "verified", **kw}


# ═══════════════════════════════════════════════════════════
# unresolved 모순 검사
#
# 모델이 자기가 뽑아놓고 "논의되지 않았습니다"라고 적는 경우가 있다.
# unresolved는 작성자가 "이건 회의에서 안 정했구나"를 판단하는 근거라,
# 거짓이면 논의된 내용이 묻힌다. 없는 걸 지어내는 것만큼 나쁘다.
# ═══════════════════════════════════════════════════════════


def test_추출해놓고_미논의라고_적으면_해당_문구를_제거한다():
    data = {
        "requirements": {"non_functional": [_req("주요 화면 응답 3초 이내")]},
        "unresolved": ["비기능 요구사항의 성능 기준이 논의되지 않았습니다."],
    }

    notes = check_unresolved_consistency(data)

    assert data["unresolved"] == []
    assert len(notes) == 1
    assert "제거했습니다" in notes[0]
    assert "requirements.non_functional" in notes[0]


def test_비기능_요구사항_거짓_주장은_기능_쪽으로_오분류되지_않는다():
    """
    2026-09-16: "기능 요구사항"이 "비기능 요구사항"의 부분 문자열이라,
    "성능"류 키워드 없이 "비기능 요구사항"만 언급하면 코드가 엉뚱하게
    (비어있는) requirements.functional을 확인하고 "모순 없음"으로
    잘못 판단해 거짓 unresolved 문구가 안 지워지던 버그의 회귀 테스트.
    """
    data = {
        "requirements": {
            "functional": [],
            "non_functional": [_req("응답 3초 이내")],
        },
        "unresolved": ["비기능 요구사항이 논의되지 않았습니다."],
    }

    notes = check_unresolved_consistency(data)

    assert data["unresolved"] == []
    assert len(notes) == 1
    assert "requirements.non_functional" in notes[0]


def test_순수_기능_요구사항_모순은_여전히_잡힌다():
    """"비"가 안 붙은 순수 "기능 요구사항" 모순은 그대로 잡혀야 한다."""
    data = {
        "requirements": {
            "functional": [_req("바코드 입출고 등록")],
            "non_functional": [],
        },
        "unresolved": ["기능 요구사항이 논의되지 않았습니다."],
    }

    notes = check_unresolved_consistency(data)

    assert data["unresolved"] == []
    assert len(notes) == 1
    assert "requirements.functional" in notes[0]


def test_실제로_비어_있으면_미논의_문구를_보존한다():
    """
    정당한 미논의까지 지우면 안 된다.
    작성자가 보완해야 할 항목을 알 수 없게 된다.
    """
    data = {
        "requirements": {"non_functional": []},
        "unresolved": ["비기능 요구사항의 성능 기준이 논의되지 않았습니다."],
    }

    notes = check_unresolved_consistency(data)

    assert data["unresolved"] == [
        "비기능 요구사항의 성능 기준이 논의되지 않았습니다."
    ]
    assert notes == []


def test_영역_키워드가_없는_문구는_건드리지_않는다():
    """판정 근거가 없으면 손대지 않는다. 모호할 때는 보존이 안전하다."""
    data = {
        "requirements": {"functional": [_req("바코드 입출고 등록")]},
        "unresolved": ["예산 규모는 추후 확정하기로 했습니다."],
    }

    notes = check_unresolved_consistency(data)

    assert len(data["unresolved"]) == 1
    assert notes == []


def test_영역_키워드만_겹치고_미논의_주장이_없으면_보존한다():
    """
    2026-09-16: 영역 키워드(예: "데이터")만 겹치면 무조건 모순으로 보던
    버그의 회귀 테스트. "데이터 보관 기간은 다음 회의에서 결정한다"는
    "데이터 요구사항 자체가 안 나왔다"는 주장이 아니라 세부 사항을
    미루는 정당한 미결정 사항이므로 지워지면 안 된다.
    """
    data = {
        "requirements": {"data": [_req("수집한 원본은 오브젝트 스토리지에 저장한다")]},
        "unresolved": ["데이터 보관 기간은 다음 회의에서 결정한다."],
    }

    notes = check_unresolved_consistency(data)

    assert data["unresolved"] == ["데이터 보관 기간은 다음 회의에서 결정한다."]
    assert notes == []


def test_모순된_것만_제거하고_나머지는_남긴다():
    data = {
        "requirements": {
            "non_functional": [_req("응답 3초 이내")],
            "data": [],
        },
        "unresolved": [
            "성능 기준이 논의되지 않았습니다.",      # 모순 — 제거
            "데이터 보관 기간이 정해지지 않았습니다.",  # 정당 — 보존
        ],
    }

    notes = check_unresolved_consistency(data)

    assert len(data["unresolved"]) == 1
    assert "데이터" in data["unresolved"][0]
    assert len(notes) == 1


# ═══════════════════════════════════════════════════════════
# check() 의 나머지 규칙
# ═══════════════════════════════════════════════════════════


def test_기술_결정이_있는데_기술_요구사항이_비면_기록한다():
    """
    기술을 정했는데 기술 요구사항이 비어 있으면 추출이 한쪽만 된 것이다.
    6번 기술 스택 섹션이 비는 원인이 되므로 확인이 필요하다.
    """
    data = {
        "requirements": {"technical": []},
        "decisions": [{"category": "tech", "content": "React를 사용한다",
                       "evidence": {"quote": "React를 사용한다"},
                       "evidence_status": "verified"}],
    }

    notes = check(data)

    assert any("기술 요구사항이 비어 있습니다" in n for n in notes)


def test_기술_요구사항이_있으면_기록하지_않는다():
    data = {
        "requirements": {"technical": [_req("React를 사용한다")]},
        "decisions": [{"category": "tech", "content": "React를 사용한다",
                       "evidence": {"quote": "React를 사용한다"},
                       "evidence_status": "verified"}],
    }

    notes = check(data)

    assert not any("기술 요구사항이 비어 있습니다" in n for n in notes)


def test_같은_내용이_다른_분류에_중복되면_기록한다():
    """
    한 내용이 두 분류에 들어가면 기획서에서 같은 문장이 두 번 나온다.
    공백만 다른 경우도 같은 내용으로 본다.
    """
    data = {
        "requirements": {
            "non_functional": [_req("모바일 우선 반응형으로 설계한다")],
            "technical": [_req("모바일  우선  반응형으로 설계한다")],
        },
    }

    notes = check(data)

    assert any("중복 등록" in n for n in notes)


def test_같은_분류_안의_중복은_기록하지_않는다():
    """분류 간 혼선을 보는 규칙이므로 같은 분류 안은 대상이 아니다."""
    data = {
        "requirements": {
            "non_functional": [_req("응답 3초 이내"), _req("응답 3초 이내")],
        },
    }

    notes = check(data)

    assert not any("중복 등록" in n for n in notes)


def test_항목_수가_폭주하면_기록한다():
    """프롬프트가 통제를 벗어났을 때의 신호다."""
    data = {
        "requirements": {
            "functional": [_req(f"기능 {i}") for i in range(MAX_ITEMS_PER_CATEGORY + 1)],
        },
    }

    notes = check(data)

    assert any("비정상적으로 많습니다" in n for n in notes)


def test_정상_범위면_폭주로_기록하지_않는다():
    data = {
        "requirements": {
            "functional": [_req(f"기능 {i}") for i in range(MAX_ITEMS_PER_CATEGORY)],
        },
    }

    notes = check(data)

    assert not any("비정상적으로 많습니다" in n for n in notes)
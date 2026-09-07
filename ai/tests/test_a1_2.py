"""
노드 ② 나열형 섹션(6, 7번) 조립 테스트.

LLM을 부르지 않으므로 빠르고 무료입니다.
list_builder의 조립 규칙을 손볼 때 여기서 회귀를 잡으세요.

## 이 테스트가 지키는 것

1. 소제목 4개가 원본 유무에 따라 나타나고 사라진다
2. 한 섹션 안에서 같은 문장이 두 번 나오지 않는다
3. 코드 조립이라 몇 번 돌려도 결과가 같다
4. HTML 이스케이프가 동작한다
"""

import pytest


from plan_draft.list_builder import build_decisions, build_tech_scope
from plan_draft.schemas import SectionType


def _structured(**overrides) -> dict:
    """회의록 1번과 비슷한 형태의 구조화 JSON."""
    data = {
        "meeting_id": "M-TEST",
        "requirements": {
            "functional": [],
            "non_functional": [
                {"content": "주요 화면 응답 3초 이내",
                 "evidence": {"quote": "응답 3초 이내를 기준으로 한다"}},
            ],
            "data": [
                {"content": "입출고 이력 테이블에 전부 기록",
                 "evidence": {"quote": "이력 테이블에 쌓는 방식으로 간다"}},
            ],
            "technical": [
                {"content": "백엔드는 Spring Boot",
                 "evidence": {"quote": "백엔드 Spring Boot"}},
            ],
        },
        "decisions": [
            {"category": "tech", "content": "Next.js는 채택하지 않는다",
             "rationale": "SEO 요구 없음",
             "evidence": {"quote": "Next.js는 채택하지 않는다"}},
            {"category": "scope", "content": "매출 예측은 MVP에서 제외",
             "rationale": None,
             "evidence": {"quote": "매출 예측 기능은 MVP 범위에서 제외하고"}},
            {"category": "feature", "content": "바코드 입출고 등록을 포함한다",
             "rationale": None,
             "evidence": {"quote": "바코드 입출고 등록"}},
        ],
        "constraints": [
            {"type": "일정", "content": "개발 기간 3개월",
             "evidence": {"quote": "개발 기간은 3개월이다"}},
        ],
        "unresolved": [],
    }
    data.update(overrides)
    return data


# ─────────────────────────────────────────────────────────────
# 6번 — 소제목 구성
# ─────────────────────────────────────────────────────────────

def test_소제목_4개가_모두_나온다():
    s = build_tech_scope(_structured())
    for title in ["기술 스택", "성능·보안 요구", "데이터 요구", "제약사항"]:
        assert title in s.content_html, f"{title} 누락"


def test_원본이_없는_소제목은_표시되지_않는다():
    """
    회의록 2번처럼 기술·데이터 논의가 없으면
    해당 소제목이 아예 안 나와야 합니다.
    """
    s = build_tech_scope(_structured(
        requirements={
            "functional": [],
            "non_functional": [{"content": "속도는 느리지 않게",
                                "evidence": {"quote": "속도는 너무 느리지 않게"}}],
            "data": [],
            "technical": [],
        },
        decisions=[],
    ))
    assert "성능·보안 요구" in s.content_html
    assert "기술 스택" not in s.content_html
    assert "데이터 요구" not in s.content_html


def test_기술스택에_tech_결정을_넣지_않는다():
    """
    decisions[tech]는 6번에 넣지 않습니다.
    같은 내용이 표현만 달라 중복되고, 7번에 어차피 들어갑니다.
    """
    s = build_tech_scope(_structured())
    assert "Next.js는 채택하지 않는다" not in s.content_html


def test_feature_결정은_6번에_들어가지_않는다():
    """6번은 기술·성능·데이터·제약만. 기능은 4번과 7번이 다룹니다."""
    s = build_tech_scope(_structured())
    assert "바코드 입출고 등록을 포함한다" not in s.content_html


def test_제약사항에_type_라벨이_붙는다():
    s = build_tech_scope(_structured())
    assert "[일정] 개발 기간 3개월" in s.content_html


def test_scope_결정은_라벨_없이_제약사항에_들어간다():
    """constraints는 type이 있고 scope 결정은 없습니다."""
    s = build_tech_scope(_structured())
    assert "매출 예측은 MVP에서 제외" in s.content_html


# ─────────────────────────────────────────────────────────────
# 6번 — 섹션 내 중복 제거
# ─────────────────────────────────────────────────────────────

def test_같은_문장이_두_번_나오지_않는다():
    """
    회의록 3번에서 발견된 문제입니다.
    "POS 연동은 A사만 유지한다"가 technical과 decisions[scope] 양쪽에
    잡혀서 기술 스택과 제약사항에 같은 문장이 두 번 나왔습니다.

    먼저 나온 소제목에 남기고 이후에는 건너뜁니다.
    """
    dup = "POS 연동은 A사만 유지하고 B사는 2차 개발로 이관한다"
    s = build_tech_scope(_structured(
        requirements={
            "functional": [], "non_functional": [], "data": [],
            "technical": [{"content": dup, "evidence": {"quote": "POS 연동은 A사만"}}],
        },
        decisions=[{"category": "scope", "content": dup, "rationale": None,
                    "evidence": {"quote": "POS 연동은 A사만"}}],
        constraints=[],
    ))
    assert s.content_html.count(dup) == 1
    assert len(s.items) == len(set(s.items))


def test_공백만_다른_문장도_중복으로_본다():
    s = build_tech_scope(_structured(
        requirements={
            "functional": [], "non_functional": [], "data": [],
            "technical": [{"content": "백엔드는 Spring Boot",
                           "evidence": {"quote": "백엔드 Spring Boot"}}],
        },
        decisions=[{"category": "scope", "content": "백엔드는  Spring  Boot",
                    "rationale": None, "evidence": {"quote": "백엔드 Spring Boot"}}],
        constraints=[],
    ))
    assert len(s.items) == 1


def test_중복_제거가_멀쩡한_항목을_지우지_않는다():
    """회의록 1·2번처럼 중복이 없던 경우 결과가 그대로여야 합니다."""
    s = build_tech_scope(_structured())
    # technical 1 + non_functional 1 + data 1 + constraints 1 + scope 결정 1
    assert len(s.items) == 5
    assert len(s.items) == len(set(s.items))
    assert "백엔드는 Spring Boot" in s.items
    assert "주요 화면 응답 3초 이내" in s.items
    assert "입출고 이력 테이블에 전부 기록" in s.items


# ─────────────────────────────────────────────────────────────
# 6번 — 빈 값 처리
# ─────────────────────────────────────────────────────────────

def test_원본이_전부_비면_is_incomplete가_True():
    s = build_tech_scope(_structured(
        requirements={"functional": [], "non_functional": [], "data": [], "technical": []},
        decisions=[], constraints=[],
    ))
    assert s.is_incomplete is True
    assert s.content_html == ""
    assert s.items == []


# ─────────────────────────────────────────────────────────────
# 7번 — 최종 결정사항
# ─────────────────────────────────────────────────────────────

def test_결정사항에_분류_라벨이_붙는다():
    s = build_decisions(_structured())
    assert "[기술]" in s.content_html
    assert "[범위]" in s.content_html
    assert "[기능]" in s.content_html


def test_rationale이_있으면_붙는다():
    s = build_decisions(_structured())
    assert "SEO 요구 없음" in s.content_html


def test_rationale이_없으면_안_붙는다():
    s = build_decisions(_structured())
    line = [i for i in s.items if "매출 예측" in i][0]
    assert "—" not in line


def test_결정사항이_없으면_비어있음():
    s = build_decisions(_structured(decisions=[]))
    assert s.is_incomplete is True
    assert s.items == []


# ─────────────────────────────────────────────────────────────
# 공통
# ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("builder", [build_tech_scope, build_decisions])
def test_코드_조립은_몇_번_돌려도_같다(builder):
    """
    게이트 A에서 나열형 섹션에 반려 버튼을 주지 않는 근거입니다.
    재생성해도 결과가 같으므로 PM이 눌러도 달라지는 게 없습니다.
    """
    data = _structured()
    first = builder(data).content_html
    for _ in range(3):
        assert builder(data).content_html == first


@pytest.mark.parametrize("builder", [build_tech_scope, build_decisions])
def test_section_type이_list다(builder):
    assert builder(_structured()).section_type == SectionType.LIST


def test_HTML_이스케이프():
    s = build_tech_scope(_structured(
        constraints=[{"type": "기타", "content": "<script>alert(1)</script>",
                      "evidence": {"quote": "테스트 문장입니다"}}],
    ))
    assert "<script>" not in s.content_html
    assert "&lt;script&gt;" in s.content_html


def test_items와_content_html이_같은_내용을_담는다():
    """
    items는 하류 노드(③)가 파싱 없이 쓰는 필드입니다.
    content_html에 있는 항목이 items에도 다 있어야 합니다.
    """
    s = build_tech_scope(_structured())
    for item in s.items:
        # 이스케이프 전 원문 기준으로 확인
        assert item.split("] ")[-1][:10] in s.content_html

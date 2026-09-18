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

    requirements = data.get("requirements") or {}
    for category in [
        "functional",
        "non_functional",
        "data",
        "technical",
    ]:
        for item in requirements.get(category, []) or []:
            item.setdefault("evidence_status", "verified")

    for category in ["decisions", "constraints"]:
        for item in data.get(category, []) or []:
            item.setdefault("evidence_status", "verified")

    return data


# ─────────────────────────────────────────────────────────────
# 6번 — 소제목 구성
# ─────────────────────────────────────────────────────────────

def test_소제목_4개가_모두_나온다():
    s = build_tech_scope(_structured())
    for title in ["기술 스택", "비기능 요구사항", "데이터 요구", "일정·인력 제약"]:
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
    assert "비기능 요구사항" in s.content_html
    assert "기술 스택" not in s.content_html
    assert "데이터 요구" not in s.content_html


def test_기술스택에_tech_결정을_함께_넣는다():
    """
    decisions[tech]도 6번 기술 스택에 넣습니다.

    바코드 구현 방식처럼 결정으로만 잡히는 기술이 빠지면
    개발자가 6번만 보고는 무엇으로 만드는지 알 수 없습니다.
    """
    s = build_tech_scope(_structured())
    assert "Next.js는 채택하지 않는다" in s.content_html


def test_요구사항과_같은_근거를_쓴_tech_결정은_중복으로_뺀다():
    """
    같은 사실이 요구사항과 결정에 표현만 다르게 들어가는 일이 흔합니다.

    문장이 다르면 seen_lines가 못 거르므로 원문 근거로 한 번 더 거릅니다.
    """
    같은_근거 = "백엔드 Spring Boot"

    s = build_tech_scope(_structured(
        requirements={
            "technical": [{
                "content": "백엔드는 Spring Boot를 사용한다",
                "evidence": {"quote": 같은_근거},
                "evidence_status": "verified",
            }],
        },
        decisions=[{
            "category": "tech",
            "content": "백엔드 기술은 Spring Boot로 확정한다",
            "rationale": "",
            "evidence": {"quote": 같은_근거},
            "evidence_status": "verified",
        }],
        constraints=[],
    ))

    assert "백엔드는 Spring Boot를 사용한다" in s.content_html
    assert "백엔드 기술은 Spring Boot로 확정한다" not in s.content_html


def test_근거가_다른_tech_결정은_남긴다():
    """근거가 다르면 다른 논의이므로 별도 항목으로 봅니다."""
    s = build_tech_scope(_structured(
        requirements={
            "technical": [{
                "content": "백엔드는 Spring Boot를 사용한다",
                "evidence": {"quote": "백엔드 Spring Boot"},
                "evidence_status": "verified",
            }],
        },
        decisions=[{
            "category": "tech",
            "content": "바코드 스캔은 BarcodeDetector로 구현한다",
            "rationale": "스캐너 구매 비용 때문",
            "evidence": {"quote": "브라우저의 BarcodeDetector API를 쓰면"},
            "evidence_status": "verified",
        }],
        constraints=[],
    ))

    assert "바코드 스캔은 BarcodeDetector로 구현한다" in s.content_html
    # 6번에는 이유를 붙이지 않습니다. 이유는 7번의 몫입니다.
    assert "스캐너 구매 비용 때문" not in s.content_html


def test_feature_결정은_6번에_들어가지_않는다():
    """6번은 기술·성능·데이터·제약만. 기능은 4번과 7번이 다룹니다."""
    s = build_tech_scope(_structured())
    assert "바코드 입출고 등록을 포함한다" not in s.content_html


def test_제약사항에_type_라벨이_붙는다():
    s = build_tech_scope(_structured())
    assert "[일정] 개발 기간 3개월" in s.content_html


def test_scope_결정은_6번에_중복되지_않는다():
    """scope 결정은 7번 최종 결정사항에서만 표시합니다."""
    s = build_tech_scope(_structured())
    assert "매출 예측은 MVP에서 제외" not in s.content_html


# ─────────────────────────────────────────────────────────────
# 6번 — groups (소제목 단위 구조화, 프론트 구조화 편집용)
# ─────────────────────────────────────────────────────────────

def test_groups에_원본이_있는_소제목만_들어간다():
    s = build_tech_scope(_structured())
    subtitles = [g.subtitle for g in s.groups]
    assert subtitles == ["기술 스택", "비기능 요구사항", "데이터 요구", "일정·인력 제약"]


def test_groups의_items가_content_html의_해당_소제목_항목과_같다():
    s = build_tech_scope(_structured())
    tech_group = next(g for g in s.groups if g.subtitle == "기술 스택")
    assert tech_group.items == [
        "백엔드는 Spring Boot",
        "Next.js는 채택하지 않는다",
    ]

    scope_group = next(g for g in s.groups if g.subtitle == "일정·인력 제약")
    assert "[일정] 개발 기간 3개월" in scope_group.items
    assert "매출 예측은 MVP에서 제외" not in scope_group.items


def test_원본이_없는_소제목은_groups에도_없다():
    s = build_tech_scope(_structured(
        requirements={
            "functional": [],
            "non_functional": [{"content": "속도는 느리지 않게",
                                "evidence": {"quote": "속도는 너무 느리지 않게"}}],
            "data": [],
            "technical": [],
        },
        decisions=[], constraints=[],
    ))
    subtitles = [g.subtitle for g in s.groups]
    assert subtitles == ["비기능 요구사항"]


def test_groups의_items_총합이_flat_items와_같다():
    """groups는 items를 소제목별로 나눈 것뿐, 내용이 달라지면 안 됩니다."""
    s = build_tech_scope(_structured())
    flat_from_groups = [i for g in s.groups for i in g.items]
    assert flat_from_groups == s.items


def test_원본이_전부_비면_groups도_빈_배열():
    s = build_tech_scope(_structured(
        requirements={"functional": [], "non_functional": [], "data": [], "technical": []},
        decisions=[], constraints=[],
    ))
    assert s.groups == []


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
    # technical 1 + decisions[tech] 1 + non_functional 1 + data 1 + constraints 1
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
    """
    2026-09-17: content_html은 대괄호 태그 대신 소제목으로 묶어 로그처럼
    반복되지 않게 바꿨다(가독성 개선). items는 ai/requirement_draft
    (node③, field_roles.yaml의 TAG_GATED 규칙)가 "[범위]" 태그를 직접
    파싱하므로 그대로 유지한다 — 두 표현이 다른 것이 이 테스트의 요점이다.
    """
    s = build_decisions(_structured())
    assert "기술 관련 결정" in s.content_html
    assert "범위 관련 결정" in s.content_html
    assert "기능 관련 결정" in s.content_html
    assert "[기술]" not in s.content_html

    assert any(item.startswith("[기술]") for item in s.items)
    assert any(item.startswith("[범위]") for item in s.items)
    assert any(item.startswith("[기능]") for item in s.items)


def test_새_결정사항_분류에_라벨이_붙는다():
    s = build_decisions(
        _structured(
            decisions=[
                {
                    "category": "non_functional",
                    "content": "응답 시간은 3초 이내로 한다",
                    "evidence": {"quote": "응답 시간은 3초 이내로 한다"},
                },
                {
                    "category": "data",
                    "content": "재고 변경 이력을 저장한다",
                    "evidence": {"quote": "재고 변경 이력을 저장한다"},
                },
            ]
        )
    )

    assert "비기능 관련 결정" in s.content_html
    assert "데이터 관련 결정" in s.content_html
    assert any(item.startswith("[비기능 요구사항]") for item in s.items)
    assert any(item.startswith("[데이터]") for item in s.items)


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


def test_context_flag가_있는_결정은_본문에서_빠지고_PM_확인사항으로만_남는다():
    """
    2026-09-18: 7번은 6번보다 엄격하게 검증한다("최종 결정사항 엄격 검증"
    요청서 참고). fact_check가 과도한 확정 서술로 표시(context_flag)한
    항목은 제안·논의 수준일 가능성이 높으므로, 6번처럼 본문에 표시만
    붙이는 게 아니라 본문에서 완전히 빼고 PM 확인 사항으로만 보여준다.
    """
    s = build_decisions(
        _structured(
            decisions=[
                {
                    "category": "scope",
                    "content": "리셀은 크림을 우선 소스로 수집한다",
                    "rationale": None,
                    "evidence": {"quote": "일단 크림 먼저 보죠"},
                    "context_flag": "근거보다 과도하게 확정적으로 서술 — 제안 수준으로만 논의됨",
                },
                {
                    "category": "tech",
                    "content": "Next.js는 채택하지 않는다",
                    "rationale": "SEO 요구 없음",
                    "evidence": {"quote": "Next.js는 채택하지 않는다"},
                },
            ]
        )
    )

    body_html, _, review_html = s.content_html.partition("PM 확인 사항")
    assert "리셀은 크림을 우선 소스로 수집한다" not in body_html
    assert "리셀은 크림을 우선 소스로 수집한다" in review_html
    assert "Next.js는 채택하지 않는다" in body_html
    assert "제안 수준으로만 논의됨" in review_html
    assert "제안 수준으로만 논의됨" in s.needs_input

    # items(node③이 파싱하는 태그 형식)는 그대로 둔다 — 두 항목 다 남는다.
    assert any("리셀은 크림을 우선 소스로 수집한다" in item for item in s.items)


def test_unverified_항목은_지워지지_않고_표시만_붙는다():
    """
    2026-09-16: unverified라고 항목을 지우면, 내용은 맞게 뽑혔는데
    인용문 한 글자 오차로 결정사항이 조용히 사라지는 사례가 실측으로
    확인됐습니다. 이제 지우지 않고 '(근거 확인 필요)' 표시만 붙입니다.
    """
    s = build_tech_scope(
        _structured(
            requirements={
                "functional": [],
                "non_functional": [
                    {
                        "content": "근거 없는 응답 시간 기준",
                        "evidence": {"quote": "원문에 없는 근거"},
                        "evidence_status": "unverified",
                    }
                ],
                "data": [],
                "technical": [],
            },
            decisions=[],
            constraints=[],
        )
    )

    assert s.items == ["근거 없는 응답 시간 기준"]
    assert s.is_incomplete is False
    assert "확인" in s.needs_input

    decisions = build_decisions(
        _structured(
            decisions=[
                {
                    "category": "feature",
                    "content": "근거 없는 기능을 제공한다",
                    "evidence": {"quote": "원문에 없는 근거"},
                    "evidence_status": "unverified",
                }
            ]
        )
    )

    assert decisions.items == [
        "[기능] 근거 없는 기능을 제공한다 (근거 확인 필요)"
    ]
    assert "확인" in decisions.needs_input


def test_context_flag가_있으면_원문_확인_필요_표시가_붙는다():
    """
    2026-09-17: meeting_analysis.fact_check가 항목에 붙인 context_flag를
    그대로 옮겨 화면에 보여줍니다. (근거 확인 필요)와는 다른 뜻입니다 —
    인용문 자체는 원문에 있지만(evidence_status=verified) 그 인용이
    항목의 확정적인 서술을 실제로 뒷받침하는지 의심스럽다는 표시입니다.
    """
    s = build_tech_scope(
        _structured(
            requirements={
                "functional": [],
                "non_functional": [],
                "data": [],
                "technical": [
                    {
                        "content": "가격 중요 시 동일 등급 기준 최저가를 보유한다",
                        "evidence": {"quote": "가격 중요하다고 하셨죠"},
                        "evidence_status": "verified",
                        "context_flag": "근거보다 과도하게 확정적으로 서술 — 회의에서는 제안 수준으로만 논의됨",
                    }
                ],
            },
            decisions=[],
            constraints=[],
        )
    )

    assert s.items == ["가격 중요 시 동일 등급 기준 최저가를 보유한다"]
    # 근거 자체는 검증됐으므로 본문·PM 확인 사항 어디에도 '(근거 확인 필요)'는 붙지 않습니다.
    assert "근거 확인 필요" not in s.items[0]
    assert "근거 확인 필요" not in s.needs_input
    assert "근거보다 과도하게 확정적으로 서술" in s.needs_input


def test_context_flag가_없으면_평소대로_표시된다():
    s = build_tech_scope(
        _structured(
            requirements={
                "functional": [], "non_functional": [], "data": [],
                "technical": [
                    {
                        "content": "백엔드는 Spring Boot",
                        "evidence": {"quote": "백엔드 Spring Boot"},
                        "evidence_status": "verified",
                    }
                ],
            },
            decisions=[], constraints=[],
        )
    )

    assert s.items == ["백엔드는 Spring Boot"]


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
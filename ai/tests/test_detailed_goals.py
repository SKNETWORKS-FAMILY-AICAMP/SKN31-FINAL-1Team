"""
세부 목표 및 문제 정의 조립 테스트.

실제 OpenAI API는 호출하지 않습니다.

검증 대상:
    plan_draft.list_builder.build_goals

2026-09-15: 문제-목표를 원문 quote 완전 일치로 짝짓던 예전 방식을
없앴습니다(실측: 항목이 1개만 남는 경우가 잦았음). 이제 LLM이
project.problem_items·project.goals를 보고 직접 title/problem/goal을
정리하면 그대로 받아들이고, 근거는 항목별이 아니라 섹션 전체 단위로
검증된 원문을 붙입니다. 이 파일은 그 새 동작을 검증합니다.

검증 내용:
    title/problem/goal이 모두 있으면 채택
    셋 중 하나라도 비면 제외
    중복 항목(문제·목표 정규화 기준) 제거
    개수 상한 없음
    섹션 근거는 project.problem_items·project.goals의 verified 원문만 사용
    LLM 결과가 비어 있으면 검증된 문제만으로 폴백
    HTML 이스케이프 처리
"""

from plan_draft.list_builder import (
    AI_SUGGESTED_GOAL_SUFFIX,
    GOAL_NOT_DISCUSSED_PLACEHOLDER,
    GOALS_NOT_DISCUSSED_NOTE,
    build_goals,
)
from plan_draft.schemas import DetailedGoal


def _detailed_goal(
    *,
    title: str = "발주 시점 누락 및 품절 방지",
    problem: str = "수기 관리로 발주 시점을 놓쳐 품절이 발생한다.",
    goal: str = "재고 임계치 알림으로 발주 누락과 품절을 줄인다.",
    matched_goal_index: int | None = None,
) -> DetailedGoal:
    """테스트용 DetailedGoal을 만듭니다."""
    return DetailedGoal(
        title=title,
        problem=problem,
        goal=goal,
        matched_goal_index=matched_goal_index,
    )


def _structured(
    *,
    problem_quote: str = "수기 관리로 발주 시점을 놓쳐 품절이 발생하고 있습니다.",
    goal_quote: str = "재고 임계치 알림을 제공하기로 했습니다.",
    problem_status: str = "verified",
    goal_status: str = "verified",
) -> dict:
    """검증된 문제와 목표를 가진 구조화 JSON을 만듭니다."""
    return {
        "project": {
            "problem": "발주 시점 누락으로 품절이 발생한다",
            "problem_evidence": {"quote": problem_quote},
            "problem_evidence_status": problem_status,
            "problem_items": [
                {
                    "content": "수기 관리로 발주 시점을 놓쳐 품절이 발생한다",
                    "evidence": {"quote": problem_quote},
                    "evidence_status": problem_status,
                }
            ],
            "goals": [
                {
                    "content": "발주 시점 누락과 품절을 줄인다",
                    "evidence": {"quote": goal_quote},
                    "evidence_status": goal_status,
                }
            ],
        },
        "requirements": {"functional": []},
        "decisions": [],
    }


def test_accepts_goal_with_title_problem_and_goal():
    """title/problem/goal이 모두 있으면 채택합니다."""
    section = build_goals(_structured(), [_detailed_goal()])

    assert section.no == 3
    assert section.key == "goals"
    assert section.title == "세부 목표 및 문제 정의"
    assert section.is_incomplete is False

    assert len(section.items) == 1
    assert "발주 시점 누락 및 품절 방지" in section.content_html
    assert "<strong>문제:</strong>" in section.content_html
    assert "<strong>목표:</strong>" in section.content_html


def test_rejects_item_missing_title():
    """title이 비어 있으면 항목에서 제외합니다."""
    generated = [_detailed_goal()]
    generated[0].title = ""

    section = build_goals(_structured(), generated)

    # title 없는 항목 하나뿐이므로 폴백(문제만 표시)으로 빠집니다.
    assert all(item.startswith("문제:") for item in section.items)
    assert "목표:" not in section.content_html


def test_removes_duplicate_problem_and_goal_pairs():
    """공백만 다른 같은 문제·목표 쌍은 한 번만 표시합니다."""
    first = _detailed_goal()
    duplicate = _detailed_goal(
        title="동일한 목표의 다른 제목",
        problem="수기  관리로 발주 시점을 놓쳐 품절이 발생한다.",
        goal="재고 임계치  알림으로 발주 누락과 품절을 줄인다.",
    )

    section = build_goals(_structured(), [first, duplicate])

    assert len(section.items) == 1
    assert section.content_html.count("<li>") == 1


def test_no_item_count_cap():
    """LLM이 여러 개를 내면 상한 없이 전부 포함합니다."""
    generated = [
        _detailed_goal(
            title=f"세부 목표 {index}",
            problem=f"문제 {index}이 발생한다.",
            goal=f"기능 {index}을 제공하여 문제를 개선한다.",
        )
        for index in range(1, 8)
    ]

    section = build_goals(_structured(), generated)

    assert len(section.items) == 7
    assert section.content_html.count("<li>") == 7
    assert "세부 목표 7" in section.content_html


def test_section_evidence_uses_verified_problem_and_goal_quotes():
    """섹션 근거는 project.problem_items·project.goals의 검증된 원문입니다."""
    structured = _structured()

    section = build_goals(structured, [_detailed_goal()])

    assert section.evidence
    assert all(e.status == "verified" for e in section.evidence)
    quotes = {e.quote for e in section.evidence}
    assert structured["project"]["problem_items"][0]["evidence"]["quote"] in quotes
    assert structured["project"]["goals"][0]["evidence"]["quote"] in quotes


def test_unverified_source_quotes_are_marked_unverified():
    """
    노드①이 unverified로 표시한 근거도 6·7번과 같은 방식으로 포함되지만
    status가 unverified로 표시됩니다(화면에서 구분 표시용) — 삭제되지 않습니다.
    """
    structured = _structured(goal_status="unverified")

    section = build_goals(structured, [_detailed_goal()])

    goal_quote = structured["project"]["goals"][0]["evidence"]["quote"]
    matching = [e for e in section.evidence if e.quote == goal_quote]

    assert matching
    assert matching[0].status == "unverified"


def test_escapes_generated_html_content():
    """LLM 결과에 HTML 문자가 있어도 실행 가능한 태그로 들어가지 않습니다."""
    generated = [
        _detailed_goal(
            title="<script>위험한 제목</script>",
            problem="<b>문제가 발생한다.</b>",
            goal="<img src=x> 문제를 개선한다.",
        )
    ]

    section = build_goals(_structured(), generated)

    assert "<script>" not in section.content_html
    assert "<b>" not in section.content_html
    assert "<img" not in section.content_html
    assert "&lt;script&gt;" in section.content_html


def test_uses_bullet_list_without_numbered_list():
    """세부 목표는 숫자 목록이 아니라 글머리 기호 목록으로 만듭니다."""
    section = build_goals(_structured(), [_detailed_goal()])

    assert section.content_html.startswith("<ul>")
    assert section.content_html.endswith("</ul>")
    assert "<li>" in section.content_html
    assert "<ol>" not in section.content_html


def test_empty_generated_goals_falls_back_to_verified_problems():
    """LLM 결과가 비어 있으면 검증된 문제만으로 폴백합니다."""
    section = build_goals(_structured(), [])

    assert section.items == [
        "문제: 수기 관리로 발주 시점을 놓쳐 품절이 발생한다",
    ]
    assert "문제:" in section.content_html
    assert "목표:" not in section.content_html
    assert section.is_incomplete is True
    assert section.needs_input == GOALS_NOT_DISCUSSED_NOTE


def test_fallback_keeps_only_verified_problem_evidence():
    """폴백이 실어 나르는 근거도 노드①이 검증한 것뿐입니다."""
    section = build_goals(_structured(), [])

    assert section.evidence
    assert all(e.status == "verified" for e in section.evidence)


def test_fallback_when_no_problem_items_returns_empty_section():
    """검증된 문제조차 없으면 섹션이 비고 is_incomplete가 True입니다."""
    structured = _structured()
    structured["project"]["problem_items"] = []

    section = build_goals(structured, [])

    assert section.items == []
    assert section.content_html == ""
    assert section.is_incomplete is True


def test_원본이_완전히_비어있으면_LLM_생성_항목도_거부한다():
    """
    2026-09-16: Codex가 재현한 사례의 회귀 테스트. project.problem_items·
    goals가 둘 다 verified 없이 완전히 비어 있으면, LLM이 title/problem/
    goal을 멀쩡하게 채워 냈어도 받아들이면 안 된다 — 근거가 0건인데
    is_incomplete=False로 "완료"처럼 보이는 건 이 섹션의 신뢰 전제를
    깬다.
    """
    structured = {
        "project": {"problem": "", "problem_items": [], "goals": []},
        "requirements": {"functional": []},
        "decisions": [],
    }
    generated = [_detailed_goal(
        title="임의 생성 목표",
        problem="임의로 만든 문제",
        goal="임의로 만든 목표",
    )]

    section = build_goals(structured, generated)

    assert section.items == []
    assert section.evidence == []
    assert section.is_incomplete is True


# ─────────────────────────────────────────────────────────────
# 2026-09-16 추가 — matched_goal_index (index-citation)
#
# LLM에게 목표 문장을 자기 말로 옮겨 적게 하는 대신, project.goals의
# 번호만 답하게 하고 코드가 유효성을 검증한다. 유효하면 화면에 보여줄
# 목표 문장 자체를 검증된 원문으로 교체하고, 무효/미제공이면 LLM이 쓴
# 문장을 AI_SUGGESTED_GOAL_SUFFIX 표시와 함께 그대로 쓴다.
# ─────────────────────────────────────────────────────────────


def test_유효한_인덱스면_목표_문장을_원문으로_교체한다():
    """LLM이 뭐라고 쓰든, 인덱스가 유효하면 project.goals 원문이 채택된다."""
    structured = _structured()
    generated = [_detailed_goal(
        goal="LLM이 다르게 옮겨 적은 문장",
        matched_goal_index=0,
    )]

    section = build_goals(structured, generated)

    assert "발주 시점 누락과 품절을 줄인다" in section.content_html
    assert "LLM이 다르게 옮겨 적은 문장" not in section.content_html
    assert AI_SUGGESTED_GOAL_SUFFIX not in section.content_html


def test_인덱스가_없으면_LLM_목표_대신_고정_문구가_쓰인다():
    """
    2026-09-17: matched_goal_index가 없으면(None) LLM이 쓴 goal 텍스트를
    신뢰하지 않는다. 실측(웹 테스트)에서 plan_generation.yaml의 예전
    지시("문제가 해소된 상태를 서술")를 따라 모든 항목이 문제를 기계적으로
    반전한 목표가 되는 문제가 확인됐다. 이제 이 경로에서는 LLM의 텍스트를
    버리고 코드가 고정 문구로 대체한다 — 아무것도 지어내지 않았으므로
    AI_SUGGESTED_GOAL_SUFFIX는 붙지 않는다.
    """
    structured = _structured()
    generated = [_detailed_goal(
        goal="회의에 없던 문맥 보완 목표",
        matched_goal_index=None,
    )]

    section = build_goals(structured, generated)

    assert "회의에 없던 문맥 보완 목표" not in section.content_html
    assert GOAL_NOT_DISCUSSED_PLACEHOLDER in section.content_html
    assert AI_SUGGESTED_GOAL_SUFFIX not in section.content_html


def test_범위를_벗어난_인덱스는_고정_문구로_대체된다():
    """
    인덱스가 project.goals 범위를 벗어나면(예: 음수, 목록 길이 이상)
    검증 실패로 보고 fail-closed 처리한다 — 있지도 않은 번호를 유효하다고
    믿으면 안 된다. 이때도 LLM의 goal 텍스트는 쓰지 않는다.
    """
    structured = _structured()
    generated = [_detailed_goal(
        goal="엉뚱한 번호를 인용한 목표",
        matched_goal_index=5,
    )]

    section = build_goals(structured, generated)

    assert "엉뚱한 번호를 인용한 목표" not in section.content_html
    assert GOAL_NOT_DISCUSSED_PLACEHOLDER in section.content_html


def test_unverified_목표는_인덱스로_인용할_수_없다():
    """
    goals_for_citation은 verified 목표만 번호를 매긴다. project.goals에
    unverified 항목이 섞여 있으면 verified 항목만 세어 인덱스가
    매겨지므로, unverified 목표는 애초에 인용 대상이 아니다.
    """
    structured = _structured(goal_status="unverified")
    generated = [_detailed_goal(
        goal="검증 안 된 목표를 인용한 척",
        matched_goal_index=0,
    )]

    section = build_goals(structured, generated)

    # verified 목표가 하나도 없으므로 인덱스 0은 항상 무효 → 고정 문구로 대체.
    assert "검증 안 된 목표를 인용한 척" not in section.content_html
    assert GOAL_NOT_DISCUSSED_PLACEHOLDER in section.content_html


# ─────────────────────────────────────────────────────────────
# 2026-09-16 추가 — 미인용 검증 목표 진단(무료, LLM 재호출 없음)
#
# matched_goal_index 인프라를 그대로 재사용해, 검증됐지만 어떤
# 세부 목표에도 인용되지 않은 project.goals 원문이 있으면
# needs_input에 확인 문구를 남긴다.
# ─────────────────────────────────────────────────────────────


def _structured_with_two_goals() -> dict:
    return {
        "project": {
            "problem": "발주 시점 누락으로 품절이 발생한다",
            "problem_items": [],
            "goals": [
                {
                    "content": "발주 시점 누락과 품절을 줄인다",
                    "evidence": {"quote": "발주 시점을 놓쳐 품절이 발생한다."},
                    "evidence_status": "verified",
                },
                {
                    "content": "인용되지 않는 두 번째 목표",
                    "evidence": {"quote": "아무도 인용하지 않을 두 번째 목표 원문이다."},
                    "evidence_status": "verified",
                },
            ],
        },
        "requirements": {"functional": []},
        "decisions": [],
    }


def test_인용되지_않은_검증_목표는_needs_input에_표시된다():
    structured = _structured_with_two_goals()
    generated = [_detailed_goal(matched_goal_index=0)]

    section = build_goals(structured, generated)

    assert "인용되지 않는 두 번째 목표" in section.needs_input


def test_모든_검증_목표가_인용되면_needs_input이_비어있다():
    structured = _structured_with_two_goals()
    generated = [
        _detailed_goal(matched_goal_index=0),
        _detailed_goal(
            title="두 번째 목표 제목",
            problem="두 번째 문제",
            goal="인용되지 않는 두 번째 목표",
            matched_goal_index=1,
        ),
    ]

    section = build_goals(structured, generated)

    assert section.needs_input == ""

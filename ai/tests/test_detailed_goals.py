"""
세부 목표 및 문제 정의 조립 테스트.

실제 OpenAI API는 호출하지 않습니다.

검증 대상:
    plan_draft.list_builder.build_goals

검증 내용:
    문제 근거와 목표 근거가 모두 검증된 경우 채택
    문제 근거가 잘못된 경우 제외
    목표 근거가 잘못된 경우 제외
    unverified 근거 제외
    중복 항목 제거
    최대 4개 제한
    근거의 줄바꿈과 공백 정규화
    HTML 글머리 기호와 이스케이프 처리
"""

from plan_draft.list_builder import build_goals
from plan_draft.schemas import DetailedGoal
from shared.schemas_base import Evidence


def _evidence(quote: str) -> Evidence:
    """테스트용 Evidence를 만듭니다."""
    return Evidence(quote=quote)


def _detailed_goal(
    *,
    title: str = "발주 시점 누락 및 품절 방지",
    problem: str = "수기 관리로 발주 시점을 놓쳐 품절이 발생한다.",
    goal: str = "재고 임계치 알림으로 발주 누락과 품절을 줄인다.",
    problem_quote: str = (
        "수기 관리로 발주 시점을 놓쳐 "
        "품절이 발생하고 있습니다."
    ),
    goal_quote: str = (
        "재고 임계치 알림을 제공하기로 했습니다."
    ),
) -> DetailedGoal:
    """테스트용 DetailedGoal을 만듭니다."""
    return DetailedGoal(
        title=title,
        problem=problem,
        goal=goal,
        problem_evidence=[
            _evidence(problem_quote)
        ],
        goal_evidence=[
            _evidence(goal_quote)
        ],
    )


def _structured(
    *,
    problem_quote: str = (
        "수기 관리로 발주 시점을 놓쳐 "
        "품절이 발생하고 있습니다."
    ),
    goal_quote: str = (
        "재고 임계치 알림을 제공하기로 했습니다."
    ),
    problem_status: str = "verified",
    goal_status: str = "verified",
) -> dict:
    """검증된 문제와 목표를 가진 구조화 JSON을 만듭니다."""
    return {
        "project": {
            "problem": "발주 시점 누락으로 품절이 발생한다",
            "problem_evidence": {
                "quote": problem_quote,
            },
            "problem_evidence_status": problem_status,
            "problem_items": [
                {
                    "content": (
                        "수기 관리로 발주 시점을 놓쳐 "
                        "품절이 발생한다"
                    ),
                    "evidence": {
                        "quote": problem_quote,
                    },
                    "evidence_status": problem_status,
                }
            ],
            "goals": [
                {
                    "content": (
                        "발주 시점 누락과 품절을 줄인다"
                    ),
                    "evidence": {
                        "quote": goal_quote,
                    },
                    "evidence_status": goal_status,
                }
            ],
        },
        "requirements": {
            "functional": [],
        },
        "decisions": [],
    }


def test_accepts_goal_with_verified_problem_and_goal_evidence():
    """문제와 목표 근거가 모두 verified이면 채택합니다."""
    structured = _structured()
    generated = [_detailed_goal()]

    section = build_goals(
        structured,
        generated,
    )

    assert section.no == 3
    assert section.key == "goals"
    assert section.title == "세부 목표 및 문제 정의"
    assert section.is_incomplete is False

    assert len(section.items) == 1
    assert len(section.evidence) == 2

    assert all(
        evidence.status == "verified"
        for evidence in section.evidence
    )

    assert (
        "발주 시점 누락 및 품절 방지"
        in section.content_html
    )
    assert (
        "<strong>문제:</strong>"
        in section.content_html
    )
    assert (
        "<strong>목표:</strong>"
        in section.content_html
    )


def test_rejects_goal_when_problem_evidence_is_not_in_source():
    """LLM이 만든 문제 근거가 원본에 없으면 항목을 제외합니다."""
    structured = _structured()

    generated = [
        _detailed_goal(
            problem_quote=(
                "원본 구조화 JSON에 없는 문제 근거입니다."
            )
        )
    ]

    section = build_goals(
        structured,
        generated,
    )

    # 채택이 0건이면 문제 정의만 싣는 폴백이 동작합니다.
    # 중요한 건 "항목이 0개"가 아니라 "지어낸 목표가 없다"입니다.
    assert all(item.startswith("문제:") for item in section.items)
    assert "목표:" not in section.content_html
    assert section.is_incomplete is True


def test_rejects_goal_when_goal_evidence_is_not_in_source():
    """LLM이 만든 목표 근거가 원본에 없으면 항목을 제외합니다."""
    structured = _structured()

    generated = [
        _detailed_goal(
            goal_quote=(
                "AI가 자동으로 재고를 예측하기로 했습니다."
            )
        )
    ]

    section = build_goals(
        structured,
        generated,
    )

    # 채택이 0건이면 문제 정의만 싣는 폴백이 동작합니다.
    # 중요한 건 "항목이 0개"가 아니라 "지어낸 목표가 없다"입니다.
    assert all(item.startswith("문제:") for item in section.items)
    assert "목표:" not in section.content_html
    assert section.is_incomplete is True


def test_rejects_unverified_problem_evidence():
    """문제 근거가 unverified이면 항목을 제외합니다."""
    structured = _structured(
        problem_status="unverified",
    )

    section = build_goals(
        structured,
        [_detailed_goal()],
    )

    assert section.items == []
    assert section.is_incomplete is True


def test_rejects_unverified_goal_evidence():
    """목표 근거가 unverified이면 항목을 제외합니다."""
    structured = _structured(
        goal_status="unverified",
    )

    section = build_goals(
        structured,
        [_detailed_goal()],
    )

    # 채택이 0건이면 문제 정의만 싣는 폴백이 동작합니다.
    # 중요한 건 "항목이 0개"가 아니라 "지어낸 목표가 없다"입니다.
    assert all(item.startswith("문제:") for item in section.items)
    assert "목표:" not in section.content_html
    assert section.is_incomplete is True


def test_rejects_functional_requirement_as_goal_evidence():
    """기능 요구사항을 임의로 문제의 목표와 연결하지 않습니다."""
    goal_quote = (
        "오전 반차와 오후 반차 선택 항목을 추가합니다."
    )

    structured = {
        "project": {
            "problem": (
                "반차 신청에서 오전과 오후 구분이 누락된다"
            ),
            "problem_evidence": {
                "quote": (
                    "반차 신청에서 오전과 오후 구분이 "
                    "누락되고 있습니다."
                )
            },
            "problem_evidence_status": "verified",
            "problem_items": [
                {
                    "content": (
                        "반차 신청에서 오전과 오후 구분이 "
                        "누락된다"
                    ),
                    "evidence": {
                        "quote": (
                            "반차 신청에서 오전과 오후 구분이 "
                            "누락되고 있습니다."
                        )
                    },
                    "evidence_status": "verified",
                }
            ],
            "goals": [],
        },
        "requirements": {
            "functional": [
                {
                    "content": (
                        "오전 반차와 오후 반차를 "
                        "선택할 수 있게 한다"
                    ),
                    "evidence": {
                        "quote": goal_quote,
                    },
                    "evidence_status": "verified",
                }
            ]
        },
        "decisions": [],
    }

    generated = [
        _detailed_goal(
            title="반차 신청 정보 누락 방지",
            problem=(
                "반차 신청에서 오전과 오후 구분이 누락된다."
            ),
            goal=(
                "반차 유형을 선택할 수 있게 하여 "
                "신청 정보 누락을 줄인다."
            ),
            problem_quote=(
                "반차 신청에서 오전과 오후 구분이 "
                "누락되고 있습니다."
            ),
            goal_quote=goal_quote,
        )
    ]

    section = build_goals(
        structured,
        generated,
    )

    # 목표가 없는 회의록이므로 문제 정의만 남습니다(폴백).
    # 중요한 건 "항목이 0개"가 아니라 "지어낸 목표가 없다"입니다.
    assert all(item.startswith("문제:") for item in section.items)
    assert "목표:" not in section.content_html
    assert goal_quote not in section.content_html
    assert section.is_incomplete is True


def test_rejects_feature_decision_as_goal_evidence():
    """기능 결정을 임의로 문제의 목표와 연결하지 않습니다."""
    goal_quote = (
        "알림 기능은 이번 개발 범위에 포함합니다."
    )

    structured = _structured()

    # project.goals의 근거를 제거하고 feature 결정만 남깁니다.
    structured["project"]["goals"] = []
    structured["decisions"] = [
        {
            "category": "feature",
            "content": "알림 기능을 추가한다",
            "evidence": {
                "quote": goal_quote,
            },
            "evidence_status": "verified",
        }
    ]

    generated = [
        _detailed_goal(
            goal_quote=goal_quote,
        )
    ]

    section = build_goals(
        structured,
        generated,
    )

    # 목표가 없는 회의록이므로 문제 정의만 남습니다(폴백).
    # 중요한 건 "항목이 0개"가 아니라 "지어낸 목표가 없다"입니다.
    assert all(item.startswith("문제:") for item in section.items)
    assert "목표:" not in section.content_html
    assert goal_quote not in section.content_html
    assert section.is_incomplete is True


def test_does_not_accept_tech_decision_as_goal_evidence():
    """tech 결정은 세부 목표의 목표 근거로 사용할 수 없습니다."""
    goal_quote = "백엔드는 Django를 사용합니다."

    structured = _structured()
    structured["project"]["goals"] = []
    structured["decisions"] = [
        {
            "category": "tech",
            "content": "백엔드는 Django를 사용한다",
            "evidence": {
                "quote": goal_quote,
            },
            "evidence_status": "verified",
        }
    ]

    generated = [
        _detailed_goal(
            goal_quote=goal_quote,
        )
    ]

    section = build_goals(
        structured,
        generated,
    )

    # tech 결정은 목표로 승격되지 않습니다.
    # 목표가 없는 회의록이므로 문제 정의만 남습니다(폴백).
    assert all(item.startswith("문제:") for item in section.items)
    assert "목표:" not in section.content_html
    assert goal_quote not in section.content_html
    assert section.is_incomplete is True


def test_removes_duplicate_problem_and_goal_pairs():
    """공백만 다른 같은 문제와 목표는 한 번만 표시합니다."""
    structured = _structured()

    first = _detailed_goal()

    duplicate = _detailed_goal(
        title="동일한 목표의 다른 제목",
        problem=(
            "수기  관리로 발주 시점을 놓쳐 "
            "품절이 발생한다."
        ),
        goal=(
            "재고 임계치  알림으로 "
            "발주 누락과 품절을 줄인다."
        ),
    )

    section = build_goals(
        structured,
        [
            first,
            duplicate,
        ],
    )

    assert len(section.items) == 1
    assert section.content_html.count("<li>") == 1


def test_limits_detailed_goals_to_four_items():
    """LLM 결과가 많아도 최대 4개만 기획서에 포함합니다."""
    problem_items = []
    project_goals = []
    generated_goals = []

    for index in range(1, 6):
        problem_quote = (
            f"문제 {index}이 발생하고 있습니다."
        )
        goal_quote = (
            f"기능 {index}을 제공하기로 했습니다."
        )

        problem_items.append(
            {
                "content": f"문제 {index}이 발생한다",
                "evidence": {
                    "quote": problem_quote,
                },
                "evidence_status": "verified",
            }
        )

        project_goals.append(
            {
                "content": f"문제 {index}을 개선한다",
                "evidence": {
                    "quote": goal_quote,
                },
                "evidence_status": "verified",
            }
        )

        generated_goals.append(
            _detailed_goal(
                title=f"세부 목표 {index}",
                problem=f"문제 {index}이 발생한다.",
                goal=f"기능 {index}을 제공하여 문제를 개선한다.",
                problem_quote=problem_quote,
                goal_quote=goal_quote,
            )
        )

    structured = {
        "project": {
            "problem": "여러 문제가 발생한다",
            "problem_items": problem_items,
            "goals": project_goals,
        },
        "requirements": {
            "functional": [],
        },
        "decisions": [],
    }

    section = build_goals(
        structured,
        generated_goals,
    )

    assert len(section.items) == 4
    assert section.content_html.count("<li>") == 4
    assert "세부 목표 4" in section.content_html
    assert "세부 목표 5" not in section.content_html


def test_evidence_comparison_normalizes_whitespace():
    """근거의 줄바꿈과 연속 공백 차이는 허용합니다."""
    source_problem_quote = (
        "수기 관리로 발주 시점을 놓쳐\n"
        "품절이 발생하고 있습니다."
    )

    submitted_problem_quote = (
        "수기 관리로 발주 시점을 놓쳐 "
        "품절이 발생하고 있습니다."
    )

    structured = _structured(
        problem_quote=source_problem_quote,
    )

    generated = [
        _detailed_goal(
            problem_quote=submitted_problem_quote,
        )
    ]

    section = build_goals(
        structured,
        generated,
    )

    assert len(section.items) == 1

    # 최종 근거에는 노드 1이 가진 원래 문장을 저장합니다.
    assert (
        section.evidence[0].quote
        == source_problem_quote
    )


def test_escapes_generated_html_content():
    """LLM 결과에 HTML 문자가 있어도 실행 가능한 태그로 들어가지 않습니다."""
    structured = _structured()

    generated = [
        _detailed_goal(
            title="<script>위험한 제목</script>",
            problem="<b>문제가 발생한다.</b>",
            goal="<img src=x> 문제를 개선한다.",
        )
    ]

    section = build_goals(
        structured,
        generated,
    )

    assert "<script>" not in section.content_html
    assert "<b>" not in section.content_html
    assert "<img" not in section.content_html

    assert (
        "&lt;script&gt;"
        in section.content_html
    )
    assert (
        "&lt;b&gt;"
        in section.content_html
    )
    assert (
        "&lt;img src=x&gt;"
        in section.content_html
    )


def test_uses_bullet_list_without_numbered_list():
    """세부 목표는 숫자 목록이 아니라 글머리 기호 목록으로 만듭니다."""
    section = build_goals(
        _structured(),
        [_detailed_goal()],
    )

    assert section.content_html.startswith("<ul>")
    assert section.content_html.endswith("</ul>")
    assert "<li>" in section.content_html
    assert "<ol>" not in section.content_html


def test_empty_generated_goals_returns_incomplete_section():
    """노드 2 결과가 비어 있으면 미완성 섹션을 반환합니다."""
    section = build_goals(
        _structured(),
        [],
    )

    # 채택이 0건이면 문제 정의만 싣는 폴백이 동작합니다.
    # 중요한 건 "항목이 0개"가 아니라 "지어낸 목표가 없다"입니다.
    assert all(item.startswith("문제:") for item in section.items)
    assert "목표:" not in section.content_html
    assert section.is_incomplete is True


# ─────────────────────────────────────────────────────────────
# 2026-09-13 추가
#
# 목표가 논의되지 않은 회의록의 폴백과, 노드 1/2의 근거 정규화
# 기준 불일치를 막는 테스트입니다.
# ─────────────────────────────────────────────────────────────


def _structured_without_goals() -> dict:
    """목표는 없고 문제만 있는 구조화 JSON — 범위 확정 회의의 전형입니다."""
    structured = _structured()
    structured["project"]["goals"] = []
    return structured


def test_falls_back_to_problems_when_no_goal_was_discussed():
    """노드 1에 목표가 없으면 섹션을 비우지 않고 문제 정의만 싣습니다."""
    section = build_goals(_structured_without_goals(), [])

    assert section.items == [
        "문제: 수기 관리로 발주 시점을 놓쳐 품절이 발생한다",
    ]
    assert "문제:" in section.content_html
    assert "목표:" not in section.content_html


def test_fallback_marks_section_incomplete_and_explains_why():
    """폴백은 미완성 상태를 유지하고 작성자에게 이유를 알려줍니다."""
    section = build_goals(_structured_without_goals(), [])

    assert section.is_incomplete is True
    assert "목표가 논의되지 않아" in section.needs_input
    assert "목표가 논의되지 않아" in section.content_html


def test_fallback_keeps_only_verified_problem_evidence():
    """폴백이 실어 나르는 근거도 노드 1이 검증한 것뿐입니다."""
    section = build_goals(_structured_without_goals(), [])

    assert section.evidence
    assert all(e.status == "verified" for e in section.evidence)


def test_fallback_note_distinguishes_why_goals_are_missing():
    """
    폴백 문구로 원인을 구분합니다.

    목표가 아예 없었던 경우와, 목표는 뽑혔는데 문제와 연결되지 않은
    경우는 작성자가 취할 조치가 다릅니다. 같은 회의록이라도 실행에 따라
    양쪽이 다 나오므로 문구로 구분해 둡니다.
    """
    from plan_draft.list_builder import (
        GOALS_NOT_DISCUSSED_NOTE,
        GOALS_UNMATCHED_NOTE,
    )

    no_goals = build_goals(_structured_without_goals(), [])
    assert no_goals.needs_input == GOALS_NOT_DISCUSSED_NOTE

    unmatched = build_goals(
        _structured(goal_status="unverified"),
        [_detailed_goal()],
    )
    assert unmatched.needs_input == GOALS_UNMATCHED_NOTE
    assert all(item.startswith("문제:") for item in unmatched.items)

def test_fallback_limits_problems_to_four_items():
    """폴백도 3번의 항목 상한 4개를 지킵니다."""
    structured = _structured_without_goals()
    structured["project"]["problem_items"] = [
        {
            "content": f"문제 {index}",
            "evidence": {"quote": f"문제 {index}가 있습니다."},
            "evidence_status": "verified",
        }
        for index in range(6)
    ]

    section = build_goals(structured, [])

    assert len(section.items) == 4


def test_fallback_uses_problem_summary_when_no_problem_items():
    """개별 문제가 없으면 전체 문제 요약이라도 싣습니다."""
    structured = _structured_without_goals()
    structured["project"]["problem_items"] = []

    section = build_goals(structured, [])

    assert section.items == [
        "문제: 발주 시점 누락으로 품절이 발생한다",
    ]


def test_fallback_skips_unverified_problem_summary():
    """요약의 근거가 unverified면 폴백도 아무것도 싣지 않습니다."""
    structured = _structured(problem_status="unverified")
    structured["project"]["goals"] = []
    structured["project"]["problem_items"] = []

    section = build_goals(structured, [])

    assert section.items == []
    assert section.is_incomplete is True


def test_evidence_matching_ignores_punctuation_like_node1():
    """
    노드 2의 근거 대조는 노드 1의 검증기와 같은 기준을 씁니다.

    노드 1은 문장부호를 제거하고 대조하므로, 노드 2가 인용을 옮기며
    마침표 하나를 빠뜨렸다고 항목이 통째로 사라지면 안 됩니다.
    """
    structured = _structured()

    generated = [
        _detailed_goal(
            problem_quote=(
                "수기 관리로 발주 시점을 놓쳐 품절이 발생하고 있습니다"
            ),
            goal_quote="재고 임계치 알림을 제공하기로 했습니다",
        )
    ]

    section = build_goals(structured, generated)

    assert len(section.items) == 1
    # 최종 기획서에는 노드 1의 원래 인용이 들어갑니다.
    assert any(
        e.quote.endswith("품절이 발생하고 있습니다.")
        for e in section.evidence
    )
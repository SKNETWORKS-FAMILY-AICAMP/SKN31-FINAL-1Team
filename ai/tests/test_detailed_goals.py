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

    assert section.items == []
    assert section.content_html == ""
    assert section.evidence == []
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

    assert section.items == []
    assert section.content_html == ""
    assert section.evidence == []
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

    assert section.items == []
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

    assert section.items == []
    assert section.content_html == ""
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

    assert section.items == []
    assert section.content_html == ""
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

    assert section.items == []
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

    assert section.items == []
    assert section.content_html == ""
    assert section.evidence == []
    assert section.is_incomplete is True

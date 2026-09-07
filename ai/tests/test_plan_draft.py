"""
tests/test_plan_draft.py

구조화 JSON 이 기획서 12개 항목으로 올바르게 매핑되는지 검증한다.
LLM 을 쓰지 않으므로 전부 결정적으로 확인할 수 있다.
"""

import json
from datetime import datetime

from meeting_analysis.schemas import (
    Evidenced,
    Meeting,
    PlanConstraint,
    PlanDecision,
    PlanDraft,
    PlanGoal,
    PlanProblem,
    PlanProject,
    PlanRequirement,
    PlanScenario,
    PlanUser,
)
from plan_draft.renderer import actor_name, render


def make_plan(**overrides) -> PlanDraft:
    """좌석알림 테스트 데이터. 문서의 기대 출력과 동일하다."""
    base = dict(
        meeting=Meeting(
            id="MTG-2026-08-25-02",
            title="스터디카페 좌석 예약 서비스 1차 기능 정의 회의",
            participants=["정하늘", "오세진", "문가영"],
            created_at=datetime(2026, 8, 25, 15, 0),
        ),
        purpose="스터디카페 좌석 예약 서비스의 1차 개발 기능과 제외 범위를 결정한다.",
        project=PlanProject(
            id="PJT-200",
            name="좌석알림",
            background=Evidenced(
                content="스터디카페 이용자가 현장에 가야만 좌석 여부를 알 수 있어 헛걸음이 발생하고 있다.",
                evidence="요즘 스터디카페는 가봐야 자리가 있는지 알 수 있어서 헛걸음하는 사람이 많다.",
            ),
            problems=[
                PlanProblem(id="PRB-001", content="이용자가 남은 좌석 수를 확인할 방법이 없다.", evidence="원문"),
                PlanProblem(id="PRB-002", content="매장 관리자가 좌석 현황을 종이 장부로 관리해 실수가 잦다.", evidence="원문"),
            ],
            goals=[
                PlanGoal(id="GOL-001", content="앱에서 실시간으로 좌석을 확인하고 예약까지 할 수 있게 한다.", evidence="원문"),
            ],
        ),
        users=[
            PlanUser(id="USER-001", type="이용자", problems=[]),
            PlanUser(id="USER-002", type="매장 관리자", problems=[]),
        ],
        requirements=[
            PlanRequirement(
                id="REQ-001", type="functional", priority="core", name="실시간 좌석 조회",
                description="이용자는 앱에서 남은 좌석을 실시간으로 확인할 수 있다.",
                actor_id="USER-001", input=[], output="", evidence="원문",
            ),
            PlanRequirement(
                id="REQ-002", type="functional", priority="core", name="좌석 예약",
                description="이용자는 좌석과 이용 시간을 지정해 예약할 수 있다.",
                actor_id="USER-001", input=["좌석", "이용 시간"], output="예약", evidence="원문",
            ),
            PlanRequirement(
                id="REQ-003", type="functional", priority="normal", name="이용 시간 연장",
                description="이용자는 이용 중에 시간을 연장할 수 있다.",
                actor_id="USER-001", input=[], output="", evidence="원문",
            ),
            PlanRequirement(
                id="REQ-004", type="functional", priority="normal", name="좌석 상태 수동 변경",
                description="매장 관리자는 청소 중인 좌석을 사용 불가로 변경할 수 있다.",
                actor_id="USER-002", input=[], output="", evidence="원문",
            ),
            PlanRequirement(
                id="REQ-005", type="non_functional", priority="normal", name="좌석 상태 반영 시간",
                description="좌석 상태 변경은 10초 이내에 앱에 반영된다.",
                actor_id="SYSTEM", input=[], output="", evidence="원문",
            ),
            PlanRequirement(
                id="REQ-006", type="data", priority="normal", name="이용 이력 보관",
                description="이용 이력은 1년간 보관한다.",
                actor_id="SYSTEM", input=[], output="", evidence="원문",
            ),
            PlanRequirement(
                id="REQ-007", type="technical", priority="normal", name="결제 연동",
                description="결제는 토스페이먼츠를 연동한다.",
                actor_id="SYSTEM", input=[], output="", evidence="원문",
            ),
        ],
        scenarios=[
            PlanScenario(
                id="SCN-001", actor_id="USER-001",
                steps=["좌석 확인", "좌석 선택", "결제", "입실", "퇴실"],
                result="좌석을 예약하고 이용을 마친다.", evidence="원문",
            ),
        ],
        decisions=[
            PlanDecision(id="DEC-001", type="feature", topic="실시간 좌석 조회",
                         decision="실시간 좌석 조회 기능을 1차 개발 범위에 포함한다.", evidence="원문"),
            PlanDecision(id="DEC-002", type="tech", topic="결제",
                         decision="토스페이먼츠를 사용한다.", evidence="원문"),
            PlanDecision(id="DEC-003", type="scope", topic="다중 지점 조회",
                         decision="여러 지점을 한 번에 보는 기능은 1차에서 제외한다.", evidence="원문"),
        ],
        constraints=[
            PlanConstraint(id="CON-001", content="한 번에 예약할 수 있는 시간은 최대 4시간이다.", evidence="원문"),
            PlanConstraint(id="CON-002", content="1차 오픈은 강남 지점 한 곳으로 한정한다.", evidence="원문"),
        ],
    )
    base.update(overrides)
    return PlanDraft(**base)


# --------------------------------------------------------------------------
# 문서 골격
# --------------------------------------------------------------------------
def test_always_twelve_sections():
    doc = render(make_plan())
    assert [s.no for s in doc.sections] == list(range(1, 13))


def test_head_uses_project_and_meeting():
    doc = render(make_plan())
    assert doc.head.title == "좌석알림"
    assert doc.head.meeting_title.startswith("스터디카페")
    assert doc.head.participants == ["정하늘", "오세진", "문가영"]


# --------------------------------------------------------------------------
# 5번과 7번의 층위 분리
# --------------------------------------------------------------------------
def test_section5_only_core_features():
    doc = render(make_plan())
    items = doc.section(5).blocks[0].items
    assert len(items) == 2
    assert [i.prefix for i in items] == ["실시간 좌석 조회", "좌석 예약"]


def test_section7_has_all_functional():
    doc = render(make_plan())
    table = doc.section(7).blocks[0]
    assert len(table.rows) == 4
    assert table.badges == ["핵심", "핵심", "", ""]


def test_section5_and_7_use_different_formats():
    """같은 형식이면 같은 내용이 두 번 실린 것처럼 보인다."""
    doc = render(make_plan())
    assert doc.section(5).blocks[0].kind == "list"
    assert doc.section(7).blocks[0].kind == "table"


# --------------------------------------------------------------------------
# 4번 대상 사용자
# --------------------------------------------------------------------------
def test_user_actions_come_from_scenarios():
    """주요 행동은 users 에 없는 값이다. 시나리오에서 끌어온다."""
    doc = render(make_plan())
    rows = doc.section(4).blocks[0].rows
    assert "좌석 확인 · 좌석 선택 · 결제 · 입실 · 퇴실" == rows[0][3]


def test_user_without_scenario_shows_dash():
    """시나리오가 없는 사용자의 행동을 지어내지 않는다."""
    doc = render(make_plan())
    rows = doc.section(4).blocks[0].rows
    assert rows[1][1] == "매장 관리자"
    assert rows[1][3] == "—"


# --------------------------------------------------------------------------
# actor_id 표시
# --------------------------------------------------------------------------
def test_actor_id_is_never_shown():
    """USER-002 같은 내부 ID 가 화면에 나가면 안 된다."""
    doc = render(make_plan())
    dumped = json.dumps(doc.model_dump(mode="json"), ensure_ascii=False)
    for section_no in (7, 8):
        table = doc.section(section_no).blocks[0]
        actor_col = table.columns.index("주체")
        for row in table.rows:
            assert not row[actor_col].startswith("USER-")
    assert "SYSTEM" not in dumped


def test_system_actor_becomes_korean():
    plan = make_plan()
    assert actor_name(plan, "SYSTEM") == "시스템"
    assert actor_name(plan, "USER-002") == "매장 관리자"


# --------------------------------------------------------------------------
# 11번과 12번 분리
# --------------------------------------------------------------------------
def test_scope_decision_only_in_section11():
    doc = render(make_plan())
    s11 = json.dumps(doc.section(11).model_dump(mode="json"), ensure_ascii=False)
    s12 = json.dumps(doc.section(12).model_dump(mode="json"), ensure_ascii=False)
    assert "다중 지점 조회" in s11
    assert "다중 지점 조회" not in s12


def test_section12_has_xref_note():
    doc = render(make_plan())
    notes = [b for b in doc.section(12).blocks if b.kind == "note"]
    assert notes and "11." in notes[0].text


def test_section12_excludes_scope():
    doc = render(make_plan())
    table = doc.section(12).blocks[0]
    assert [r[0] for r in table.rows] == ["DEC-001", "DEC-002"]


# --------------------------------------------------------------------------
# 근거 비노출
# --------------------------------------------------------------------------
def test_evidence_never_reaches_the_document():
    """evidence 는 검토·디버깅용이다. 기획서 본문에 나가지 않는다."""
    plan = make_plan()
    plan.project.background.evidence = "절대_화면에_나오면_안되는_문장"
    doc = render(plan)
    dumped = json.dumps(doc.model_dump(mode="json"), ensure_ascii=False)
    assert "절대_화면에_나오면_안되는_문장" not in dumped
    assert "evidence" not in dumped


# --------------------------------------------------------------------------
# 빈 항목 처리
# --------------------------------------------------------------------------
def test_empty_section_survives_with_message():
    """섹션이 사라지면 논의 누락을 사용자가 알 수 없다."""
    plan = make_plan()
    plan.requirements = [r for r in plan.requirements if r.type.value != "data"]
    doc = render(plan)

    s9 = doc.section(9)
    assert s9.is_empty
    assert s9.blocks == []
    assert "회의록에 없어" in s9.empty_message
    assert 9 in [s.no for s in doc.sections]


def test_toc_marks_empty_sections():
    plan = make_plan()
    plan.scenarios = []
    doc = render(plan)
    entry = next(e for e in doc.toc if e.no == 6)
    assert entry.is_empty


def test_section5_empty_points_to_section7():
    plan = make_plan()
    for r in plan.requirements:
        r.priority = "normal"
    doc = render(plan)
    assert doc.section(5).is_empty
    assert "7번" in doc.section(5).empty_message


def test_user_problems_empty_shows_dash():
    doc = render(make_plan())
    rows = doc.section(4).blocks[0].rows
    assert rows[0][2] == "—"


def test_section2_hides_user_group_when_empty():
    """사용자 문제가 없으면 사용자 관점 묶음 자체를 만들지 않는다."""
    doc = render(make_plan())
    headings = [b.heading for b in doc.section(2).blocks]
    assert headings == ["서비스 관점"]


# --------------------------------------------------------------------------
# 입출력 표기
# --------------------------------------------------------------------------
def test_io_column_formats():
    doc = render(make_plan())
    table = doc.section(7).blocks[0]
    io_col = table.columns.index("입력 / 출력")
    assert table.rows[0][io_col] == "—"                      # 둘 다 없음
    assert table.rows[1][io_col] == "좌석, 이용 시간 → 예약"  # 둘 다 있음


# --------------------------------------------------------------------------
# 결정성
# --------------------------------------------------------------------------
def test_render_is_deterministic():
    """LLM 을 쓰지 않으므로 같은 입력이면 항상 같은 출력이어야 한다."""
    a = render(make_plan()).model_dump(mode="json")
    b = render(make_plan()).model_dump(mode="json")
    assert a == b
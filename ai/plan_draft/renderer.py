"""
plan_draft/renderer.py

구조화 JSON(PlanDraft)을 기획서 12개 항목(PlanDocument)으로 바꾼다.

LLM 을 쓰지 않는다. 같은 입력이면 항상 같은 출력이 나와야 한다.
결과가 달라진다면 이 파일에 버그가 있는 것이다.

매핑 규칙의 출처는 기획서 자동생성 구조 최종안 v1.1 의 5.2 매핑표다.
"""

from __future__ import annotations

from meeting_analysis.schemas import (
    SYSTEM_ACTOR_ID,
    PlanDraft,
    PlanRequirement,
    RequirementPriority,
    RequirementType,
)

from .schemas import (
    DocumentHead,
    FieldBlock,
    FlowBlock,
    ListBlock,
    ListItem,
    NoteBlock,
    PlanDocument,
    Section,
    TableBlock,
)

# 값이 없을 때 표에 넣는 문자
DASH = "—"

# 항목별 안내 문구. 회의에서 논의되지 않았을 때 화면에 표시한다.
EMPTY_MESSAGE: dict[int, str] = {
    1: "프로젝트 개요에 해당하는 발언이 회의록에 없어 비워 두었습니다.",
    2: "문제 정의에 해당하는 발언이 회의록에 없어 비워 두었습니다.",
    3: "목표에 해당하는 발언이 회의록에 없어 비워 두었습니다.",
    4: "사용자 유형이 회의록에서 확인되지 않아 비워 두었습니다.",
    5: "핵심으로 지정된 기능이 없습니다. 전체 기능은 7번 항목을 참고하세요.",
    6: "사용자 이용 흐름이 회의록에서 확인되지 않아 비워 두었습니다.",
    7: "기능 요구사항에 해당하는 발언이 회의록에 없어 비워 두었습니다.",
    8: "비기능 요구사항에 해당하는 발언이 회의록에 없어 비워 두었습니다.",
    9: "데이터 요구사항에 해당하는 발언이 회의록에 없어 비워 두었습니다.",
    10: "기술 요구사항에 해당하는 발언이 회의록에 없어 비워 두었습니다.",
    11: "범위와 제약에 해당하는 발언이 회의록에 없어 비워 두었습니다.",
    12: "기능·기술 관련 결정이 회의록에 없어 비워 두었습니다.",
}

TITLES: dict[int, str] = {
    1: "프로젝트 개요",
    2: "문제 정의",
    3: "프로젝트 목표",
    4: "대상 사용자",
    5: "주요 기능",
    6: "사용자 시나리오",
    7: "기능 요구사항",
    8: "비기능 요구사항",
    9: "데이터 요구사항",
    10: "기술 요구사항",
    11: "서비스 범위 및 제약사항",
    12: "최종 결정사항",
}

XREF_12 = "범위와 관련된 결정은 11. 서비스 범위 및 제약사항에서 확인할 수 있습니다."


# --------------------------------------------------------------------------
# 보조 함수
# --------------------------------------------------------------------------
def actor_name(plan: PlanDraft, actor_id: str) -> str:
    """actor_id 를 화면 표시명으로 바꾼다.

    USER-002 같은 내부 ID 를 화면에 그대로 노출하지 않는다.
    """
    if actor_id == SYSTEM_ACTOR_ID:
        return "시스템"
    for u in plan.users:
        if u.id == actor_id:
            return u.type
    return actor_id


def _io(req: PlanRequirement) -> str:
    """입력과 출력을 한 칸에 담는다. 둘 다 없으면 —."""
    left = ", ".join(req.input) if req.input else ""
    if left and req.output:
        return f"{left} → {req.output}"
    if left:
        return left
    if req.output:
        return f"→ {req.output}"
    return DASH


def _by_type(plan: PlanDraft, t: RequirementType) -> list[PlanRequirement]:
    return [r for r in plan.requirements if r.type is t]


def _section(no: int, blocks: list) -> Section:
    """블록이 비면 안내 문구를 넣은 빈 섹션으로 만든다."""
    filled = [b for b in blocks if b is not None]
    is_empty = not any(_has_content(b) for b in filled)
    return Section(
        no=no,
        title=TITLES[no],
        is_empty=is_empty,
        empty_message=EMPTY_MESSAGE[no] if is_empty else "",
        blocks=[] if is_empty else filled,
    )


def _has_content(block) -> bool:
    kind = block.kind
    if kind == "field":
        return bool(block.text)
    if kind == "list":
        return bool(block.items)
    if kind == "table":
        return bool(block.rows)
    if kind == "flow":
        return bool(block.steps)
    return False  # note 만으로는 내용이 있다고 보지 않는다


# --------------------------------------------------------------------------
# 항목별 렌더링
# --------------------------------------------------------------------------
def _s1_overview(plan: PlanDraft) -> Section:
    return _section(
        1,
        [
            FieldBlock(label="프로젝트명", text=plan.project.name),
            FieldBlock(label="문서 작성 배경", text=plan.purpose),
            FieldBlock(label="프로젝트 배경", text=plan.project.background.content),
        ],
    )


def _s2_problems(plan: PlanDraft) -> Section:
    service = ListBlock(
        heading="서비스 관점",
        items=[ListItem(text=p.content) for p in plan.project.problems],
    )
    user = ListBlock(
        heading="사용자 관점",
        items=[
            ListItem(prefix=u.type, text=p.content)
            for u in plan.users
            for p in u.problems
        ],
    )
    return _section(2, [b for b in (service, user) if b.items])


def _s3_goals(plan: PlanDraft) -> Section:
    return _section(
        3, [ListBlock(items=[ListItem(text=g.content) for g in plan.project.goals])]
    )


def _s4_users(plan: PlanDraft) -> Section:
    rows = []
    for u in plan.users:
        # 주요 행동은 users 가 아니라 scenarios 에서 온다.
        # 해당 사용자의 시나리오가 없으면 비운다. 지어내지 않는다.
        actions = [
            step
            for s in plan.scenarios
            if s.actor_id == u.id
            for step in s.steps
        ]
        problems = " / ".join(p.content for p in u.problems) or DASH
        rows.append(
            [u.id, u.type, problems, " · ".join(actions) if actions else DASH]
        )

    return _section(
        4,
        [TableBlock(columns=["ID", "유형", "사용자 문제", "주요 행동"], rows=rows)],
    )


def _s5_core_features(plan: PlanDraft) -> Section:
    core = [
        r
        for r in _by_type(plan, RequirementType.FUNCTIONAL)
        if r.priority is RequirementPriority.CORE
    ]
    return _section(
        5,
        [
            ListBlock(
                items=[ListItem(prefix=r.name, text=r.description) for r in core]
            )
        ],
    )


def _s6_scenarios(plan: PlanDraft) -> Section:
    blocks = [
        FlowBlock(
            heading=f"{s.id} · {actor_name(plan, s.actor_id)}",
            steps=s.steps,
            result=s.result,
        )
        for s in plan.scenarios
    ]
    return _section(6, blocks or [FlowBlock()])


def _requirement_table(
    plan: PlanDraft,
    reqs: list[PlanRequirement],
    *,
    with_actor: bool = True,
    with_io: bool = True,
) -> TableBlock:
    columns = ["ID", "항목", "내용"]
    if with_actor:
        columns.append("주체")
    if with_io:
        columns.append("입력 / 출력")

    rows, badges = [], []
    for r in reqs:
        row = [r.id, r.name, r.description]
        if with_actor:
            row.append(actor_name(plan, r.actor_id))
        if with_io:
            row.append(_io(r))
        rows.append(row)
        badges.append("핵심" if r.priority is RequirementPriority.CORE else "")

    return TableBlock(columns=columns, rows=rows, badges=badges)


def _s7_functional(plan: PlanDraft) -> Section:
    # 5번과 달리 core 여부와 무관하게 전부, 입출력까지 상세하게
    reqs = _by_type(plan, RequirementType.FUNCTIONAL)
    return _section(7, [_requirement_table(plan, reqs)])


def _s8_non_functional(plan: PlanDraft) -> Section:
    reqs = _by_type(plan, RequirementType.NON_FUNCTIONAL)
    return _section(8, [_requirement_table(plan, reqs, with_io=False)])


def _s9_data(plan: PlanDraft) -> Section:
    reqs = _by_type(plan, RequirementType.DATA)
    return _section(9, [_requirement_table(plan, reqs, with_actor=False)])


def _s10_technical(plan: PlanDraft) -> Section:
    reqs = _by_type(plan, RequirementType.TECHNICAL)
    return _section(
        10, [_requirement_table(plan, reqs, with_actor=False, with_io=False)]
    )


def _s11_scope(plan: PlanDraft) -> Section:
    scope = ListBlock(
        heading="범위 결정",
        items=[
            ListItem(prefix=d.topic, text=d.decision)
            for d in plan.decisions
            if d.type.value == "scope"
        ],
    )
    constraints = ListBlock(
        heading="제약사항",
        items=[ListItem(text=c.content) for c in plan.constraints],
    )
    return _section(11, [b for b in (scope, constraints) if b.items])


def _s12_decisions(plan: PlanDraft) -> Section:
    # scope 는 11번에만 싣는다. 여기 넣으면 같은 내용이 두 번 나온다.
    label = {"feature": "기능", "tech": "기술"}
    rows = [
        [d.id, label[d.type.value], d.topic, d.decision]
        for d in plan.decisions
        if d.type.value in label
    ]
    section = _section(
        12,
        [TableBlock(columns=["ID", "구분", "주제", "결정 내용"], rows=rows)],
    )
    # 안내 문구는 비어 있을 때도 붙인다. 11번을 찾아가야 하는 건 같다.
    section.blocks.append(NoteBlock(text=XREF_12))
    return section


# --------------------------------------------------------------------------
# 본체
# --------------------------------------------------------------------------
def render(plan: PlanDraft) -> PlanDocument:
    """구조화 JSON 을 기획서 12개 항목으로 바꾼다."""
    head = DocumentHead(
        title=plan.project.name,
        meeting_title=plan.meeting.title,
        date=plan.meeting.created_at.strftime("%Y. %-m. %-d."),
        participants=plan.meeting.participants,
    )

    sections = [
        _s1_overview(plan),
        _s2_problems(plan),
        _s3_goals(plan),
        _s4_users(plan),
        _s5_core_features(plan),
        _s6_scenarios(plan),
        _s7_functional(plan),
        _s8_non_functional(plan),
        _s9_data(plan),
        _s10_technical(plan),
        _s11_scope(plan),
        _s12_decisions(plan),
    ]

    return PlanDocument(head=head, sections=sections)
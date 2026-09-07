"""
tests/test_meeting_analysis.py

LLM 호출 없이 후처리와 프롬프트 조립만 검증한다.
API 키가 없어도 돌아가야 한다.
"""

from datetime import datetime

import pytest

from meeting_analysis.postprocess import evidence_found, resolve_actor_id, to_plan_draft
from meeting_analysis.prompt_builder import build_system_prompt, build_user_prompt
from meeting_analysis.schemas import (
    SYSTEM_ACTOR_ID,
    Evidenced,
    ExtractedConstraint,
    ExtractedDecision,
    ExtractedProject,
    ExtractedRequirement,
    ExtractedScenario,
    ExtractedUser,
    ExtractionResult,
    Meeting,
    RequirementPriority,
    RequirementType,
)

TRANSCRIPT = """
판매자는 상품명, 가격, 설명과 사진을 입력하여 상품을 등록할 수 있도록 한다. 이건 핵심 기능이다.
구매자가 원하는 물건을 키워드로 찾을 수 있게 한다.
검색 결과는 2초 이내에 표시되어야 한다.
백엔드는 Django에 PostgreSQL로 가기로 했다.
결제는 이번에 빼고 다음 버전에서 하기로 했다.
상품 사진은 최대 5장까지 등록할 수 있도록 한다.
구매자는 상품을 검색한 후 판매자에게 채팅을 보내고 거래를 진행한다.
관리자 페이지도 있으면 좋겠다.
"""

MEETING = Meeting(
    id="MTG-2026-08-25-01",
    title="중고거래 플랫폼 개발 회의",
    participants=["김민수", "이지은"],
    created_at=datetime(2026, 8, 25, 16, 0),
)


def make_extraction(**overrides) -> ExtractionResult:
    base = dict(
        purpose="1차 개발 범위를 결정한다.",
        project=ExtractedProject(name="안심 중고거래 플랫폼"),
        users=[
            ExtractedUser(type="구매자"),
            ExtractedUser(type="판매자"),
        ],
        requirements=[
            ExtractedRequirement(
                type=RequirementType.FUNCTIONAL,
                priority=RequirementPriority.CORE,
                name="상품 등록",
                description="판매자는 상품을 등록할 수 있다.",
                actor="판매자",
                evidence="판매자는 상품명, 가격, 설명과 사진을 입력하여 상품을 등록할 수 있도록 한다.",
            ),
            ExtractedRequirement(
                type=RequirementType.NON_FUNCTIONAL,
                name="검색 응답시간",
                description="검색 결과는 2초 이내에 표시된다.",
                actor="시스템",
                evidence="검색 결과는 2초 이내에 표시되어야 한다.",
            ),
        ],
        scenarios=[
            ExtractedScenario(
                actor="구매자",
                steps=["상품 검색", "판매자에게 채팅", "거래 진행"],
                result="거래를 완료한다.",
                evidence="구매자는 상품을 검색한 후 판매자에게 채팅을 보내고 거래를 진행한다.",
            )
        ],
        decisions=[
            ExtractedDecision(
                type="tech",
                topic="백엔드",
                decision="Django와 PostgreSQL을 사용한다.",
                evidence="백엔드는 Django에 PostgreSQL로 가기로 했다.",
            )
        ],
        constraints=[
            ExtractedConstraint(
                content="상품 이미지는 최대 5장까지 등록한다.",
                evidence="상품 사진은 최대 5장까지 등록할 수 있도록 한다.",
            )
        ],
    )
    base.update(overrides)
    return ExtractionResult(**base)


def convert(extraction):
    return to_plan_draft(extraction, MEETING, TRANSCRIPT)


# --------------------------------------------------------------------------
# 1단계: ID 부여
# --------------------------------------------------------------------------
def test_ids_are_assigned_in_order():
    plan, report = convert(make_extraction())
    assert [u.id for u in plan.users] == ["USER-001", "USER-002"]
    assert [r.id for r in plan.requirements] == ["REQ-001", "REQ-002"]
    assert plan.scenarios[0].id == "SCN-001"
    assert plan.decisions[0].id == "DEC-001"
    assert plan.constraints[0].id == "CON-001"
    assert report.ok, report.summary()


# --------------------------------------------------------------------------
# 2단계: actor_id 변환
# --------------------------------------------------------------------------
def test_actor_name_becomes_user_id():
    plan, _ = convert(make_extraction())
    assert plan.requirements[0].actor_id == "USER-002"  # 판매자
    assert plan.scenarios[0].actor_id == "USER-001"  # 구매자


def test_system_actor_uses_reserved_id():
    plan, _ = convert(make_extraction())
    assert plan.requirements[1].actor_id == SYSTEM_ACTOR_ID


def test_unknown_actor_is_dropped():
    """users 에 없는 행위자는 기획서에 등장하면 안 된다."""
    extraction = make_extraction()
    extraction.requirements[0].actor = "배송기사"
    plan, report = convert(extraction)

    assert all(r.name != "상품 등록" for r in plan.requirements)
    assert any("행위자 미상" in d for d in report.dropped)


def test_resolve_actor_id_directly():
    mapping = {"구매자": "USER-001"}
    assert resolve_actor_id("구매자", mapping) == "USER-001"
    assert resolve_actor_id("시스템", mapping) == SYSTEM_ACTOR_ID
    assert resolve_actor_id("배송기사", mapping) is None
    assert resolve_actor_id("", mapping) is None


# --------------------------------------------------------------------------
# 3단계: 근거 대조
# --------------------------------------------------------------------------
def test_fabricated_item_is_dropped():
    """회의에 없는 내용을 지어내면 폐기된다. 이 시스템의 핵심 방어선."""
    extraction = make_extraction()
    extraction.requirements.append(
        ExtractedRequirement(
            type=RequirementType.NON_FUNCTIONAL,
            name="동시 접속자",
            description="동시 사용자 1,000명을 지원한다.",
            actor="시스템",
            evidence="동시 사용자 1,000명을 지원해야 한다.",  # 회의록에 없음
        )
    )
    plan, report = convert(extraction)

    assert all(r.name != "동시 접속자" for r in plan.requirements)
    assert any("근거 불일치" in d for d in report.dropped)


def test_empty_evidence_is_dropped():
    extraction = make_extraction()
    extraction.requirements[0].evidence = ""
    plan, report = convert(extraction)
    assert all(r.name != "상품 등록" for r in plan.requirements)


def test_whitespace_difference_is_tolerated():
    """LLM 이 줄바꿈이나 띄어쓰기를 바꿔도 같은 문장으로 인정한다."""
    assert evidence_found("검색  결과는\n2초 이내에 표시되어야 한다.", TRANSCRIPT)


# --------------------------------------------------------------------------
# 4단계: 중복 병합
# --------------------------------------------------------------------------
def test_near_duplicate_requirements_are_merged():
    extraction = make_extraction()
    extraction.requirements.append(
        ExtractedRequirement(
            type=RequirementType.FUNCTIONAL,
            name="상품 등록하기",
            description="판매자는 상품을 등록할 수 있다",  # 마침표만 다름
            actor="판매자",
            evidence="판매자는 상품명, 가격, 설명과 사진을 입력하여 상품을 등록할 수 있도록 한다.",
        )
    )
    plan, report = convert(extraction)

    assert len(plan.requirements) == 2
    assert any("중복 병합" in w for w in report.warnings)


# --------------------------------------------------------------------------
# 5단계: 기본값 보정
# --------------------------------------------------------------------------
def test_core_priority_only_for_functional():
    extraction = make_extraction()
    extraction.requirements[1].priority = RequirementPriority.CORE  # non_functional
    plan, report = convert(extraction)

    assert plan.requirements[1].priority is RequirementPriority.NORMAL
    assert any("보정" in w for w in report.warnings)


def test_priority_defaults_to_normal():
    req = ExtractedRequirement(
        type=RequirementType.FUNCTIONAL,
        name="테스트",
        description="테스트",
        actor="시스템",
    )
    assert req.priority is RequirementPriority.NORMAL


# --------------------------------------------------------------------------
# 시나리오 규칙
# --------------------------------------------------------------------------
def test_single_step_is_not_a_scenario():
    """행동 나열은 시나리오가 아니다. 순서가 있어야 한다."""
    extraction = make_extraction()
    extraction.scenarios[0].steps = ["상품 검색"]
    plan, report = convert(extraction)

    assert plan.scenarios == []
    assert any("단계 부족" in d for d in report.dropped)


# --------------------------------------------------------------------------
# 결측 처리
# --------------------------------------------------------------------------
def test_missing_sections_become_empty_lists():
    plan, report = convert(
        ExtractionResult(purpose="범위만 정한다.", project=ExtractedProject(name="테스트"))
    )
    assert plan.users == []
    assert plan.requirements == []
    assert plan.project.problems == []
    assert plan.project.background.content == ""
    assert report.ok


# --------------------------------------------------------------------------
# 스키마 계약
# --------------------------------------------------------------------------
def test_schema_version_is_fixed():
    plan, _ = convert(make_extraction())
    assert plan.schema_version == "1.1"


def test_undefined_field_is_rejected():
    """정의되지 않은 필드를 LLM 이 만들어내면 검증에서 걸린다."""
    with pytest.raises(Exception):
        ExtractedRequirement(
            type=RequirementType.FUNCTIONAL,
            name="테스트",
            description="테스트",
            actor="시스템",
            deadline="2026-09-01",  # 스키마에 없는 필드
        )


def test_output_matches_fixture_shape():
    """하린 담당 에이전트에 넘기는 구조와 키가 일치하는지."""
    plan, _ = convert(make_extraction())
    dumped = plan.model_dump(mode="json")

    assert set(dumped) == {
        "schema_version", "meeting", "purpose", "project",
        "users", "requirements", "scenarios", "decisions", "constraints",
    }
    assert set(dumped["requirements"][0]) == {
        "id", "type", "priority", "name", "description",
        "actor_id", "input", "output", "evidence",
    }


# --------------------------------------------------------------------------
# 프롬프트 조립
# --------------------------------------------------------------------------
def test_system_prompt_contains_core_rules():
    prompt = build_system_prompt()
    for token in ["정보 추출 AI", "non_functional", "scope", "core", "evidence", "금지"]:
        assert token in prompt


def test_user_prompt_marks_participants_as_non_users():
    prompt = build_user_prompt(TRANSCRIPT, purpose="범위 결정", participants=["김민수"])
    assert "김민수" in prompt
    assert "users 에 넣지 마십시오" in prompt
    assert "판매자는 상품명" in prompt

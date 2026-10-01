"""
tests/test_a2_1.py

LLM을 실제로 호출하지 않고도 확인할 수 있는 부분(스키마 검증 규칙,
프롬프트 조립 결과)을 테스트한다. LLM 호출 자체는 API 키가 있는
환경에서 fixtures/sample_plan.json으로 수동 실행해 확인한다.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from requirement_draft.prompt_builder import build_system_prompt
from requirement_draft.schemas import PlanDocument, RequirementItem

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_plan() -> PlanDocument:
    data = json.loads((FIXTURES / "sample_plan_test.json").read_text(encoding="utf-8"))
    return PlanDocument.model_validate(data)


def test_prompt_contains_fixed_and_dynamic_parts(sample_plan):
    prompt = build_system_prompt(sample_plan)
    # 고정 자산이 포함되는지
    assert "[표준 비기능요구사항 체크리스트]" in prompt
    assert "[항상 생성]" in prompt
    # 동적 데이터(이번 기획서)가 포함되는지
    assert sample_plan.project_id in prompt
    assert sample_plan.requirements[0].content in prompt


@pytest.mark.parametrize(
    "overrides,expected_error",
    [
        ({"id": "FR-1-1"}, "ID 포맷"),
        ({"id": "NFR-01-001", "type": "기능"}, "type"),
        # category_1은 이제 type에서 코드가 강제로 확정하므로(2026-09-08),
        # LLM이 뭘 보내든 검증 대상이 아니다 — 대신 category_2는 기능/비기능
        # 둘 다 필수로 바뀌었으니 빈 값이면 걸려야 한다.
        ({"category_2": None}, "category_2"),
        ({"category_2": "  "}, "category_2"),
        ({"priority": None, "review_status": "검토완료"}, "priority"),
        ({"source": "baseline_default", "review_status": "검토완료"}, "baseline_default"),
    ],
)
def test_schema_rejects_rule_violations(overrides, expected_error):
    base = dict(
        id="FR-01-001",
        category_1="기능",
        category_2="문서 관리",
        title="문서 업로드",
        description="설명",
        type="기능",
        priority="High",
        source="requirement_text",
        review_status="검토완료",
    )
    base.update(overrides)
    with pytest.raises(ValidationError):
        RequirementItem(**base)



def _quality_plan() -> PlanDocument:
    return PlanDocument.model_validate(
        {
            "project_id": "102",
            "title": "ERP 연동",
            "goal": "ERP 업무를 자동화한다",
            "key_features": "ERP API 어댑터를 연동하고 사용자 피드백을 수집한다.",
            "requirements": [{"id": "REQ-01", "content": "ERP API 어댑터 연동"}],
        }
    )


def _quality_item(**overrides) -> RequirementItem:
    values = {
        "id": "FR-01-001",
        "category_1": "기능",
        "category_2": "ERP 연동",
        "title": "ERP API 요청",
        "description": "ERP API로 요청을 전달하고 결과를 반환한다.",
        "related_feature": "[key_features] ERP API 어댑터 연동",
        "input_output": "업무 요청을 입력받아 ERP API 결과를 반환한다.",
        "acceptance_criteria": "요청 결과가 반환되는지 통합 테스트로 확인한다.",
        "note": "기획서 직접 근거",
        "type": "기능",
        "priority": "High",
        "source": "requirement_text",
        "review_status": "검토완료",
    }
    values.update(overrides)
    return RequirementItem.model_validate(values)


def test_quality_gate_rejects_unsupported_scope_and_repairs_acceptance():
    from requirement_draft.agent import finalize_unresolved_quality_items
    from requirement_draft.quality import collect_requirement_quality_issues

    item = _quality_item(
        description="사용자 피드백을 개선 작업 큐에 전달한다.",
        acceptance_criteria="최소 1개 결과를 저장한다.",
    )
    issues = collect_requirement_quality_issues(_quality_plan(), [item])
    codes = {issue.code for issue in issues}

    assert "UNSUPPORTED_DESIGN" in codes
    assert "ACCEPTANCE_UNGROUNDED_NUMBER" in codes
    assert finalize_unresolved_quality_items([item], issues) == []


def test_quality_gate_accepts_grounded_objective_boolean_criteria():
    from requirement_draft.quality import collect_requirement_quality_issues

    assert collect_requirement_quality_issues(_quality_plan(), [_quality_item()]) == []


def test_agent_regenerates_failed_item_only(monkeypatch):
    from requirement_draft import agent
    from requirement_draft.schemas import RequirementDocument

    invalid = _quality_item(acceptance_criteria="후속 확정 필요")
    corrected = _quality_item()
    calls = iter(
        [
            RequirementDocument(requirements=[invalid]),
            RequirementDocument(requirements=[corrected]),
        ]
    )
    monkeypatch.setattr(agent, "create_structured", lambda **kwargs: next(calls))
    monkeypatch.setattr(agent, "verify_baseline_coverage", lambda doc: [])

    result = agent.generate_requirements(_quality_plan())

    assert result.requirements == [corrected]

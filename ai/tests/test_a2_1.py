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

from a2_1_requirement_draft.prompt_builder import build_system_prompt
from a2_1_requirement_draft.schemas import PlanDocument, RequirementItem

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_plan() -> PlanDocument:
    data = json.loads((FIXTURES / "sample_plan.json").read_text(encoding="utf-8"))
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
        ({"id": "NFR-01-001", "type": "기능", "category_2": None}, "type"),
        ({"category_2": "하위분류", "type": "비기능", "id": "NFR-01-001"}, "category_2"),
        ({"priority": None, "review_status": "검토완료"}, "priority"),
        ({"source": "baseline_default", "review_status": "검토완료"}, "baseline_default"),
    ],
)
def test_schema_rejects_rule_violations(overrides, expected_error):
    base = dict(
        id="FR-01-001",
        category_1="문서 관리",
        category_2="문서 등록",
        name="문서 업로드",
        description="설명",
        type="기능",
        priority="High",
        source="requirement_text",
        review_status="검토완료",
    )
    base.update(overrides)
    with pytest.raises(ValidationError):
        RequirementItem(**base)

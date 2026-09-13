"""결정사항 분류 스키마와 보정 규칙 테스트."""

import pytest

from meeting_analysis.schemas import (
    Decision,
    DecisionCategory,
)
from meeting_analysis.validators.cross_rules import (
    repair_feature_decision_categories,
)


@pytest.mark.parametrize(
    "category",
    [
        "feature",
        "non_functional",
        "data",
        "tech",
        "scope",
    ],
)
def test_decision_schema_accepts_all_supported_categories(
    category: str,
):
    decision = Decision.model_validate(
        {
            "category": category,
            "content": "확정된 내용",
            "evidence": {
                "quote": "확정된 내용",
            },
        }
    )

    assert decision.category == DecisionCategory(category)


@pytest.mark.parametrize(
    ("requirement_category", "expected_category"),
    [
        ("non_functional", "non_functional"),
        ("data", "data"),
        ("technical", "tech"),
    ],
)
def test_repairs_feature_decision_using_same_verified_quote(
    requirement_category: str,
    expected_category: str,
):
    quote = "확정 기준은 요청 후 3초 이내로 한다."
    data = {
        "requirements": {
            "functional": [],
            "non_functional": [],
            "data": [],
            "technical": [],
        },
        "decisions": [
            {
                "category": "feature",
                "content": "확정 기준을 적용한다.",
                "evidence": {"quote": quote},
                "evidence_status": "verified",
            }
        ],
    }
    data["requirements"][requirement_category] = [
        {
            "content": "확정 기준을 적용한다.",
            "evidence": {"quote": quote},
            "evidence_status": "verified",
        }
    ]

    notes = repair_feature_decision_categories(data)

    assert data["decisions"][0]["category"] == expected_category
    assert len(notes) == 1


def test_does_not_repair_when_same_quote_is_functional():
    quote = "문의 등록 기능을 제공한다."
    data = {
        "requirements": {
            "functional": [
                {
                    "content": "문의 등록 기능을 제공한다.",
                    "evidence": {"quote": quote},
                    "evidence_status": "verified",
                }
            ],
            "non_functional": [],
            "data": [],
            "technical": [],
        },
        "decisions": [
            {
                "category": "feature",
                "content": "문의 등록 기능을 제공한다.",
                "evidence": {"quote": quote},
                "evidence_status": "verified",
            }
        ],
    }

    notes = repair_feature_decision_categories(data)

    assert data["decisions"][0]["category"] == "feature"
    assert notes == []


def test_does_not_repair_ambiguous_or_unverified_decision():
    quote = "응답 기준과 저장 항목을 확정한다."
    shared_item = {
        "content": "기준을 확정한다.",
        "evidence": {"quote": quote},
        "evidence_status": "verified",
    }
    data = {
        "requirements": {
            "functional": [],
            "non_functional": [shared_item],
            "data": [shared_item],
            "technical": [],
        },
        "decisions": [
            {
                "category": "feature",
                "content": "기준을 확정한다.",
                "evidence": {"quote": quote},
                "evidence_status": "verified",
            },
            {
                "category": "feature",
                "content": "근거가 확인되지 않은 기준",
                "evidence": {"quote": "없는 근거"},
                "evidence_status": "unverified",
            },
        ],
    }

    notes = repair_feature_decision_categories(data)

    assert [
        decision["category"]
        for decision in data["decisions"]
    ] == ["feature", "feature"]
    assert notes == []

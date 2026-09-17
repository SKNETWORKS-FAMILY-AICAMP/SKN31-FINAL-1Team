"""
plan_generation_fewshots.yaml이 실제 PlanSections 계약과 맞는지 검증합니다.

2026-09-17: 이 파일을 추가하기 전까지 퓨샷 템플릿의 검증 로직
(prompt_loader._validate_example)을 직접 테스트하는 파일이 없었습니다.
그래서 09-15에 DetailedGoal에서 problem_evidence·goal_evidence를 삭제한
뒤로도 퓨샷 예시가 옛 필드를 계속 들고 있는 계약 불일치가 한동안
발견되지 않았습니다 — pydantic이 기본적으로 extra 필드를 무시해서
검증을 그냥 통과했기 때문입니다. 이 파일은 그 회귀를 막습니다.
"""

import copy

import pytest

from plan_draft.prompt_loader import (
    PromptTemplateError,
    _validate_fewshots_template,
    load_plan_fewshots,
)
from plan_draft.schemas import Feature, PlanSections


def test_현재_퓨샷_템플릿은_그대로_로드된다():
    """실제 파일이 지금 스키마와 맞는지 확인하는 스모크 테스트입니다."""
    template = load_plan_fewshots()
    assert template["examples"]
    assert template["glossary_examples"]


def test_퓨샷_예시가_실제_페이로드처럼_인용_목록을_포함한다():
    """
    _build_generation_payload가 실제로 주는
    feature_sources_for_citation·goals_for_citation·
    problem_sources_for_citation이 최소 한 예시의 input에는 있어야
    합니다 — 없으면 LLM이 실제로 받는 입력 모양과 다른 예시로 학습합니다.
    """
    template = load_plan_fewshots()
    example = template["examples"][0]

    assert "feature_sources_for_citation" in example["input"]
    assert "goals_for_citation" in example["input"]
    assert "problem_sources_for_citation" in example["input"]


def test_퓨샷_예시가_features와_source_indices_사용법을_보여준다():
    """
    output.features 예시가 하나도 없으면 source_indices 사용법(특히
    같은 quote로 이어진 tech/scope 결정을 인용하는 법)을 LLM에게
    보여줄 수 없습니다.
    """
    template = load_plan_fewshots()
    example = template["examples"][0]

    features = example["output"].get("features")
    assert features, "output.features 예시가 비어 있으면 안 됩니다."
    assert any(f.get("source_indices") for f in features)


def test_삭제된_필드가_남아있으면_퓨샷_검증이_실패한다():
    """
    2026-09-15에 삭제된 problem_evidence·goal_evidence가 goals 항목에
    남아 있으면 지금은 검증이 바로 실패해야 합니다(DetailedGoal의
    extra="forbid" 참고) — 예전에는 조용히 통과했습니다.
    """
    template = copy.deepcopy(load_plan_fewshots())
    template["examples"][0]["output"]["goals"][0]["problem_evidence"] = [
        {"quote": "옛날 형식"}
    ]

    with pytest.raises(PromptTemplateError):
        _validate_fewshots_template(template)


def test_features_항목에_존재하지_않는_필드가_있으면_퓨샷_검증이_실패한다():
    """Feature도 DetailedGoal과 같은 이유로 extra="forbid"를 적용했습니다."""
    template = copy.deepcopy(load_plan_fewshots())
    template["examples"][0]["output"]["features"][0]["legacy_feature_name"] = "옛 필드"

    with pytest.raises(PromptTemplateError):
        _validate_fewshots_template(template)


def test_PlanSections가_삭제된_필드를_직접_거부한다():
    """prompt_loader를 거치지 않고 스키마 자체의 계약도 확인합니다."""
    old_style = {
        "sections": [{"key": "overview", "content_html": "<p>x</p>"}],
        "goals": [
            {
                "title": "t",
                "problem": "p",
                "goal": "g",
                "problem_evidence": [{"quote": "q"}],
                "goal_evidence": [{"quote": "q"}],
            }
        ],
    }

    with pytest.raises(Exception):
        PlanSections.model_validate(old_style)


def test_Feature가_알_수_없는_필드를_거부한다():
    with pytest.raises(Exception):
        Feature(
            group="mvp",
            title="t",
            description="d",
            source_indices=[0],
            feature_name="옛 필드",
        )

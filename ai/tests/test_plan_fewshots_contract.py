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

from plan_draft.load_prompts import (
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


def test_퓨샷_예시가_AI_제안_goal_경로를_보여준다():
    """
    2026-09-17(2차): 실측에서 matched_goal_index가 없는 문제 전부 goal이
    빈 문자열로 나온 회귀를 막습니다. 대응하는 목표가 없어도(
    matched_goal_index: null) goal 필드를 채운 예시가 최소 하나는 있어야
    LLM이 이 경로를 어떻게 채우는지 모방할 대상이 생깁니다.
    """
    template = load_plan_fewshots()
    example = template["examples"][0]

    unmatched_goals = [
        g for g in example["output"]["goals"]
        if g.get("matched_goal_index") is None
    ]

    assert unmatched_goals, "matched_goal_index가 null인 goals 예시가 없습니다."
    assert all(g["goal"].strip() for g in unmatched_goals), (
        "AI 제안 경로 예시인데 goal이 비어 있습니다 — 이러면 빈 문자열이 "
        "기본값이라고 학습시키는 것과 같습니다."
    )


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

"""LLM 호출 없이 실행되는 기획서 품질 게이트와 골든 데이터 계약 테스트."""

from pathlib import Path
import json

from plan_draft.context_writer import PlanningFact, PlanningFactIndex
from plan_draft.quality_gate import evaluate_golden, inspect_plan, load_golden_cases
from plan_draft.schemas import Feature, PlanDocument, PlanSection, SectionType, VerifiedEvidence
from shared.schemas_base import Evidence


FIXTURES = Path(__file__).parent / "fixtures"


def _section(no: int, key: str, text: str, *, evidence=(), items=()):
    return PlanSection(
        no=no, key=key, title=key, section_type=SectionType.LIST,
        content_html=f"<p>{text}</p>", items=list(items), evidence=list(evidence),
    )


def _plan(section_texts: dict[str, str]) -> PlanDocument:
    keys = ["overview", "problem", "goals", "users", "features", "tech_scope", "decisions"]
    return PlanDocument(
        proposal_id="test", meeting_id="meeting",
        sections=[_section(i + 1, key, section_texts.get(key, "내용")) for i, key in enumerate(keys)],
    )


def test_golden_dataset_references_existing_sources_and_has_unique_ids():
    cases = load_golden_cases(FIXTURES / "plan_quality_golden.json")
    assert len(cases) >= 5
    assert {case.case_id for case in cases} >= {
        "complete_retail_mvp", "vague_meeting", "scenario_flow",
        "unseen_domain", "musinsa_long",
    }
    for case in cases:
        assert (FIXTURES / case.source_file).is_file()
        ids = [item.expectation_id for item in case.required + case.forbidden]
        assert len(ids) == len(set(ids))
        assert all(item.term_groups for item in case.required + case.forbidden)


def test_golden_evaluator_reports_missing_and_forbidden_meaning_anchors():
    case = next(
        item for item in load_golden_cases(FIXTURES / "plan_quality_golden.json")
        if item.case_id == "musinsa_long"
    )
    plan = _plan({
        "problem": "트렌드와 상품 수명 주기 및 리세일 지수를 분석한다.",
        "decisions": (
            "원본은 S3에 보관하고 핵심 데이터는 RDS에 저장한다. "
            "대표 용어와 동의어 테이블은 ID로 연결한다. "
            "크림을 우선 사용하고 무신사 유즈드로 보완한다. "
            "스냅샷은 하나의 테이블로 통합한다고 확정했다."
        ),
        "features": "자막 오타를 후처리 교정한다.",
    })

    result = evaluate_golden(plan, case)

    assert result.recall == 1.0
    assert set(result.forbidden_ids) == {
        "subtitle_postprocess_confirmed", "snapshot_schema_decided",
    }
    assert not result.passed


def test_quality_gate_blocks_unverified_evidence():
    plan = _plan({})
    plan.sections[0].evidence = [
        VerifiedEvidence(quote="원문에 없는 문장", status="verified"),
    ]

    report = inspect_plan(plan, "실제 원문")

    assert not report.passed
    assert [issue.code for issue in report.blocking_issues] == ["unverified_evidence"]


def test_quality_gate_blocks_proposal_promoted_to_final_decision():
    quote = "자막 오타는 후처리해야 하나 싶어요."
    evidence = VerifiedEvidence(quote=quote, status="verified")
    plan = _plan({"decisions": "자막 오타 후처리를 적용한다."})
    plan.sections[-1].evidence = [evidence]
    plan.sections[-1].items = ["[기능] 자막 오타 후처리를 적용한다."]
    index = PlanningFactIndex(facts=[PlanningFact(
        topic="자막 오타 후처리", status="proposed", content="후처리를 검토한다.",
        evidence=[Evidence(quote=quote)], section_candidates=["features", "decisions"],
    )])

    report = inspect_plan(plan, quote, index)

    assert not report.passed
    assert any(issue.code == "non_confirmed_as_decision" for issue in report.issues)


def test_quality_gate_allows_proposal_when_later_same_topic_is_confirmed():
    proposal_quote = "처음에는 앱 푸시를 제안했습니다."
    confirmed_quote = "논의 끝에 앱 내 알림함으로 확정했습니다."
    plan = _plan({"decisions": "앱 내 알림함을 사용한다."})
    plan.sections[-1].items = ["[기능] 앱 내 알림함을 사용한다."]
    plan.sections[-1].evidence = [
        VerifiedEvidence(quote=proposal_quote, status="verified"),
        VerifiedEvidence(quote=confirmed_quote, status="verified"),
    ]
    index = PlanningFactIndex(facts=[
        PlanningFact(
            topic="알림 채널", status="proposed", content="앱 푸시를 제안했다.",
            evidence=[Evidence(quote=proposal_quote)], section_candidates=["decisions"],
            source_order=1,
        ),
        PlanningFact(
            topic="알림 채널", status="confirmed", content="앱 내 알림함을 사용한다.",
            evidence=[Evidence(quote=confirmed_quote)], section_candidates=["decisions"],
            source_order=2,
        ),
    ])

    report = inspect_plan(plan, proposal_quote + " " + confirmed_quote, index)

    assert report.passed


def test_quality_gate_blocks_rejected_feature_but_allows_confirmed_evidence():
    rejected_quote = "매출 예측 기능은 MVP 범위에서 제외한다."
    confirmed_quote = "대시보드 기능을 제공한다."
    plan = _plan({"features": "매출 예측과 대시보드를 제공한다."})
    plan.sections[4].evidence = [
        VerifiedEvidence(quote=rejected_quote, status="verified"),
        VerifiedEvidence(quote=confirmed_quote, status="verified"),
    ]
    plan.sections[4].features = [Feature(
        title="매출 예측", description="판매량을 예측한다.",
        evidence=[Evidence(quote=rejected_quote)],
    )]
    index = PlanningFactIndex(facts=[
        PlanningFact(
            topic="매출 예측", status="rejected", content="MVP에서 제외한다.",
            evidence=[Evidence(quote=rejected_quote)], section_candidates=["features"],
        ),
        PlanningFact(
            topic="대시보드", status="confirmed", content="대시보드를 제공한다.",
            evidence=[Evidence(quote=confirmed_quote)], section_candidates=["features"],
        ),
    ])

    report = inspect_plan(plan, rejected_quote + " " + confirmed_quote, index)

    assert any(issue.code == "rejected_as_feature" for issue in report.blocking_issues)


def test_golden_forbidden_check_ignores_pm_review_question():
    case = next(
        item for item in load_golden_cases(FIXTURES / "plan_quality_golden.json")
        if item.case_id == "musinsa_long"
    )
    plan = _plan({
        "problem": "트렌드와 상품 수명 주기 및 리세일 지수를 분석한다.",
        "decisions": (
            "원본은 S3에 보관하고 핵심 데이터는 RDS에 저장한다. "
            "대표 용어와 동의어 테이블을 ID로 연결한다. "
            "크림을 우선 사용하고 무신사 유즈드로 보완한다."
        ),
    })
    decision = plan.sections[-1]
    decision.needs_input = "Top-2 태그 부여 기준을 확정해야 합니다."
    decision.content_html += (
        "<p><strong>PM 확인 사항</strong></p><ul>"
        "<li>Top-2 태그 부여 기준을 확정해야 합니다.</li></ul>"
    )

    result = evaluate_golden(plan, case)

    assert "top2_as_final_decision" not in result.forbidden_ids


def test_saved_plan_can_be_loaded_and_evaluated_without_llm(tmp_path):
    plan = _plan({
        "problem": "트렌드와 상품 수명 주기 및 리세일 지수를 분석한다.",
        "decisions": (
            "원본은 오브젝트 스토리지에 보관하고 핵심 데이터는 RDS에 저장한다. "
            "대표 용어와 동의어 테이블을 ID로 연결한다. "
            "KREAM을 우선 사용하고 무신사 유즈드로 보완한다."
        ),
    })
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")
    loaded = PlanDocument.model_validate_json(path.read_text(encoding="utf-8"))
    case = next(
        item for item in load_golden_cases(FIXTURES / "plan_quality_golden.json")
        if item.case_id == "musinsa_long"
    )

    result = evaluate_golden(loaded, case)

    assert result.passed
    assert result.recall == 1.0

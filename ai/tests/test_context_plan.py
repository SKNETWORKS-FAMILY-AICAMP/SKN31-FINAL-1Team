"""원문 기반 1~4번 생성 경로. 실제 API 호출 없는 계약·조립 검증."""

import json

import pytest
from pydantic import ValidationError

from plan_draft import agent, generator
from plan_draft.schemas import SECTION_SPEC
from shared.schemas_base import Evidence


SOURCE = "상품은 A몰을 기준으로 합니다. 주목적은 트렌드 분석입니다. 완전 자동화가 목표입니다."
QUOTE_1 = "상품은 A몰을 기준으로 합니다."
QUOTE_2 = "주목적은 트렌드 분석입니다."


def _draft(key):
    """SOURCE에 실제로 있는 인용 2개를 물고 있는 섹션별 초안을 만듭니다."""
    evidence = [Evidence(quote=QUOTE_1), Evidence(quote=QUOTE_2)]

    if key == "overview":
        para = generator.CitedParagraph(
            text="상품 정보와 반응을 연결해 분석한다.", evidence=evidence,
        )
        empty = generator.CitedParagraph(text="")
        return generator.OverviewDraft(
            service_overview=para, data_scope=empty, current_and_future=empty,
        )
    if key == "problem":
        para = generator.CitedParagraph(
            text="상품 정보와 반응을 연결해 분석한다.", evidence=evidence,
        )
        empty = generator.CitedParagraph(text="")
        return generator.CoreGoalDraft(core_goal=para, approach=empty)
    if key == "goals":
        goal = generator.DetailedGoalDraft(
            title="분석 자동화", problem="수동으로 처리하고 있다.",
            direction="처리 과정을 자동화한다.", evidence=evidence,
        )
        return generator.GoalsDraft(goals=[goal])
    if key == "users":
        user = generator.UserDraft(
            name="사장님", description="상품 정보와 반응을 연결해 분석한다.",
            usage="", evidence=evidence, is_proposal=True,
        )
        return generator.UsersDraft(users=[user])
    raise ValueError(key)


def _spec(key):
    return next(s for s in SECTION_SPEC if s["key"] == key)


def test_render_keeps_multiple_quotes_and_marks_proposed_user():
    result = generator.render_section(_draft("users"), SOURCE, _spec("users"))
    assert len(result.evidence) == 2
    assert "사장님을 서비스 대상 사용자로 정의할지 확인이 필요합니다." in result.content_html
    assert "원문과 대조해 확인해 주세요" not in result.content_html


def test_proposed_user_josa_matches_batchim():
    """
    2026-09-18: "{이름}을 서비스 대상 사용자로..."가 받침 유무와 무관하게 항상
    "을"을 붙여서, "보호자을"·"이용자을"처럼 받침 없는 이름에서 조사가 틀리는
    문제가 다양한 회의록 테스트에서 재현됐다. 받침 없는 이름은 "를"이 맞다.
    """
    evidence = [Evidence(quote=QUOTE_1), Evidence(quote=QUOTE_2)]
    user = generator.UserDraft(
        name="보호자", description="환자의 복약 상황을 함께 인지한다.",
        usage="", evidence=evidence, is_proposal=True,
    )
    draft = generator.UsersDraft(users=[user])
    result = generator.render_section(draft, SOURCE, _spec("users"))
    assert "보호자를 서비스 대상 사용자로 정의할지 확인이 필요합니다." in result.content_html
    assert "보호자을" not in result.content_html


def test_missing_quote_is_not_verified_and_html_is_escaped():
    para = generator.CitedParagraph(
        text="<script>test</script>",
        evidence=[Evidence(quote="원문에 없는 인용입니다.")],
    )
    empty = generator.CitedParagraph(text="")
    draft = generator.OverviewDraft(
        service_overview=para, data_scope=empty, current_and_future=empty,
        review_questions=["<권한 확인>"],
    )
    result = generator.render_section(draft, SOURCE, _spec("overview"))
    assert result.evidence == []
    assert "원문과 대조해 확인해 주세요" in result.content_html
    assert "<script>" not in result.content_html
    assert "&lt;권한 확인&gt;" in result.content_html


def test_generation_receives_source_without_legacy_limits(monkeypatch):
    calls = []

    def call(system, messages, response_model, **kwargs):
        calls.append(response_model)
        assert len(messages) == 1
        if response_model is generator.PlanningFactIndex:
            assert SOURCE in messages[0]["content"]
            return generator.PlanningFactIndex(facts=[
                generator.PlanningFact(
                    topic="기준 소스", status="confirmed",
                    content="A몰을 기준 상품 소스로 사용한다.",
                    evidence=[Evidence(quote=QUOTE_2)],
                    section_candidates=["overview", "decisions"],
                    source_order=1,
                )
            ])
        technical = generator.TechnicalDecisionPlan(
            tech_scope=generator.TechScopeDraft(groups=[
                generator.TechGroupDraft(
                    title="데이터·저장 방침",
                    items=[generator.CitedListItem(
                        text="A몰을 기준 상품 소스로 사용한다.",
                        evidence=[Evidence(quote=QUOTE_1)],
                    )],
                )
            ]),
            decisions=generator.DecisionsDraft(items=[
                generator.DecisionItemDraft(
                    category="scope",
                    content="A몰을 기준 상품 소스로 사용한다.",
                    evidence=[Evidence(quote=QUOTE_1)],
                )
            ]),
        )
        assert response_model is generator.WholePlanDraft
        payload = json.loads(messages[0]["content"])
        assert payload["meeting_source_text"] == SOURCE
        assert payload["planning_fact_index"]["facts"][0]["topic"] == "기준 소스"
        return generator.WholePlanDraft(
            context=generator.ContextPlan(
                overview=_draft("overview"),
                problem=_draft("problem"),
                goals=_draft("goals"),
                users=_draft("users"),
            ),
            features=generator.FeaturePlan(features=[
                generator.Feature(
                    title="트렌드 분석",
                    description="상품 반응을 이용해 트렌드를 분석한다.",
                    evidence=[Evidence(quote=QUOTE_2)],
                )
            ]),
            technical=technical,
        )

    monkeypatch.setattr(agent, "_call", call)
    result = agent.run(
        {"plan_source_text": SOURCE, "project": {}, "requirements": {}},
        "test", generation_strategy="indexed",
    )
    assert calls == [generator.PlanningFactIndex, generator.WholePlanDraft]
    assert len(result.sections) == 7
    for item in result.sections[:4]:
        assert len(item.evidence) == 2
        assert not item.is_incomplete
    assert result.sections[2].items
    assert result.sections[4].key == "features"
    assert result.sections[4].items == ["트렌드 분석"]
    assert result.sections[4].evidence[0].quote == QUOTE_2
    assert result.sections[5].evidence[0].quote == QUOTE_1
    assert result.sections[6].items == ["[범위] A몰을 기준 상품 소스로 사용한다."]


def test_direct_strategy_skips_fact_index_call(monkeypatch):
    calls = []
    observed_indexes = []

    def call(_system, messages, response_model, **_kwargs):
        calls.append(response_model)
        assert response_model is generator.WholePlanDraft
        payload = json.loads(messages[0]["content"])
        assert payload["meeting_source_text"] == SOURCE
        assert payload["planning_fact_index"]["facts"] == []
        technical = generator.TechnicalDecisionPlan(
            tech_scope=generator.TechScopeDraft(),
            decisions=generator.DecisionsDraft(),
        )
        return generator.WholePlanDraft(
            context=generator.ContextPlan(
                overview=_draft("overview"), problem=_draft("problem"),
                goals=_draft("goals"), users=_draft("users"),
            ),
            features=generator.FeaturePlan(), technical=technical,
        )

    monkeypatch.setattr(agent, "_call", call)
    result = agent.run(
        {"plan_source_text": SOURCE, "project": {}, "requirements": {}},
        "test", generation_strategy="direct", on_fact_index=observed_indexes.append,
    )

    assert calls == [generator.WholePlanDraft]
    assert observed_indexes == [generator.PlanningFactIndex()]
    assert len(result.sections) == 7


def test_parallel_strategy_runs_content_and_technical_calls_concurrently(monkeypatch):
    """운영 기본 경로(parallel) — 2026-09-21 인수인계 문서 4절. 호출 A
    (ContentPlanDraft: 1~5번)와 호출 B(TechnicalDecisionPlan: 6~7번)가
    사실 인덱스 없이 회의록 원문만으로 독립 실행되는지 확인한다."""
    calls = []
    observed_indexes = []

    def call(_system, messages, response_model, context=""):
        calls.append((response_model, context))
        assert len(messages) == 1
        assert messages[0]["content"] == "[회의록 원문]\n" + SOURCE
        if response_model is generator.ContentPlanDraft:
            return generator.ContentPlanDraft(
                context=generator.ContextPlan(
                    overview=_draft("overview"), problem=_draft("problem"),
                    goals=_draft("goals"), users=_draft("users"),
                ),
                features=generator.FeaturePlan(features=[
                    generator.Feature(
                        title="트렌드 분석", description="상품 반응을 이용해 트렌드를 분석한다.",
                        evidence=[Evidence(quote=QUOTE_2)],
                    )
                ]),
            )
        assert response_model is generator.TechnicalDecisionPlan
        return generator.TechnicalDecisionPlan(
            tech_scope=generator.TechScopeDraft(groups=[
                generator.TechGroupDraft(
                    title="데이터·저장 방침",
                    items=[generator.CitedListItem(
                        text="A몰을 기준 상품 소스로 사용한다.",
                        evidence=[Evidence(quote=QUOTE_1)],
                    )],
                )
            ]),
            decisions=generator.DecisionsDraft(items=[
                generator.DecisionItemDraft(
                    category="scope", content="A몰을 기준 상품 소스로 사용한다.",
                    evidence=[Evidence(quote=QUOTE_1)],
                )
            ]),
        )

    monkeypatch.setattr(agent, "_call", call)
    result = agent.run(
        {"plan_source_text": SOURCE, "project": {}, "requirements": {}},
        "test", generation_strategy="parallel", on_fact_index=observed_indexes.append,
    )

    assert {response_model for response_model, _ in calls} == {
        generator.ContentPlanDraft, generator.TechnicalDecisionPlan,
    }
    contexts = {context for _, context in calls}
    assert contexts == {"run content-plan proposal_id=test", "run technical-decisions proposal_id=test"}
    assert observed_indexes == [generator.PlanningFactIndex()]
    assert len(result.sections) == 7
    for item in result.sections[:4]:
        assert len(item.evidence) == 2
        assert not item.is_incomplete
    assert result.sections[4].key == "features"
    assert result.sections[4].items == ["트렌드 분석"]
    assert result.sections[6].items == ["[범위] A몰을 기준 상품 소스로 사용한다."]


def test_parallel_is_the_default_generation_strategy(monkeypatch):
    """백엔드는 전략 인자를 넘기지 않으므로 기본값이 곧 운영 경로다."""
    seen_models = []

    def call(_system, _messages, response_model, context=""):
        seen_models.append(response_model)
        if response_model is generator.ContentPlanDraft:
            return generator.ContentPlanDraft(
                context=generator.ContextPlan(
                    overview=_draft("overview"), problem=_draft("problem"),
                    goals=_draft("goals"), users=_draft("users"),
                ),
                features=generator.FeaturePlan(),
            )
        return generator.TechnicalDecisionPlan(
            tech_scope=generator.TechScopeDraft(), decisions=generator.DecisionsDraft(),
        )

    monkeypatch.setattr(agent, "_call", call)
    agent.run({"plan_source_text": SOURCE, "project": {}, "requirements": {}}, "test")

    assert set(seen_models) == {generator.ContentPlanDraft, generator.TechnicalDecisionPlan}


def test_long_source_is_split_on_paragraph_boundaries_for_parallel_indexing():
    source = "첫 번째 문단입니다.\n\n두 번째 문단은 조금 더 깁니다.\n\n세 번째 문단입니다."

    chunks = agent._split_source_for_index(source, limit=24)

    assert len(chunks) >= 2
    assert "".join(chunks).replace("\n", "") == source.replace("\n", "")
    assert all(len(chunk) <= 24 for chunk in chunks)


def test_fact_index_keeps_only_exact_source_quotes_and_preserves_status():
    index = generator.PlanningFactIndex(facts=[
        generator.PlanningFact(
            topic="기준 소스", status="confirmed", content="A몰을 사용한다.",
            evidence=[Evidence(quote=QUOTE_1)], section_candidates=["decisions"],
        ),
        generator.PlanningFact(
            topic="없는 기능", status="proposed", content="없는 기능을 제안했다.",
            evidence=[Evidence(quote="원문에 없는 인용")], section_candidates=["features"],
        ),
        generator.PlanningFact(
            topic="자동화", status="current_state", content="자동화가 목표다.",
            evidence=[Evidence(quote="완전 자동화가 목표입니다.")],
            section_candidates=["overview"],
        ),
    ])

    merged = generator.merge_verified_fact_indexes([index], SOURCE)

    assert [(fact.topic, fact.status) for fact in merged.facts] == [
        ("기준 소스", "confirmed"), ("자동화", "current_state"),
    ]
    assert [fact.source_order for fact in merged.facts] == [1, 2]


def test_nonfinal_filter_removes_rejected_feature_and_unresolved_decision():
    rejected_quote = "매출 예측은 이번 범위에서 제외합니다."
    unresolved_quote = "단일 테이블로 할지는 다음에 결정합니다."
    confirmed_quote = "A몰을 기준 소스로 확정합니다."
    technical = generator.TechnicalDecisionPlan(
        tech_scope=generator.TechScopeDraft(),
        decisions=generator.DecisionsDraft(items=[
            generator.DecisionItemDraft(
                category="data", content="단일 테이블로 통합한다.",
                evidence=[Evidence(quote=unresolved_quote)],
            ),
            generator.DecisionItemDraft(
                category="scope", content="A몰을 기준 소스로 사용한다.",
                evidence=[Evidence(quote=confirmed_quote)],
            ),
        ]),
    )
    draft = generator.WholePlanDraft(
        context=generator.ContextPlan(
            overview=_draft("overview"), problem=_draft("problem"),
            goals=_draft("goals"), users=_draft("users"),
        ),
        features=generator.FeaturePlan(features=[
            generator.Feature(
                title="매출 예측", description="판매량을 예측한다.",
                evidence=[Evidence(quote=rejected_quote)],
            ),
        ]),
        technical=technical,
    )
    index = generator.PlanningFactIndex(facts=[
        generator.PlanningFact(
            topic="매출 예측", status="rejected", content="범위에서 제외한다.",
            evidence=[Evidence(quote=rejected_quote)], section_candidates=["features"],
        ),
        generator.PlanningFact(
            topic="스키마", status="unresolved", content="구조는 미정이다.",
            evidence=[Evidence(quote=unresolved_quote)], section_candidates=["decisions"],
        ),
        generator.PlanningFact(
            topic="기준 소스", status="confirmed", content="A몰을 사용한다.",
            evidence=[Evidence(quote=confirmed_quote)], section_candidates=["decisions"],
        ),
    ])

    filtered = generator.filter_nonfinal_outputs(draft, index)

    assert filtered.features.features == []
    assert [item.content for item in filtered.technical.decisions.items] == [
        "A몰을 기준 소스로 사용한다."
    ]
    assert "최종 확정되지 않았으므로" in filtered.technical.decisions.review_questions[0]
    assert "제외된 기능" in filtered.technical.decisions.review_questions[1]


def test_nonfinal_filter_removes_unresolved_feature_without_confirmed_same_topic():
    quote = "앱 푸시와 문자를 얘기했지만 비용 때문에 확인이 필요합니다."
    draft = generator.WholePlanDraft(
        context=generator.ContextPlan(
            overview=_draft("overview"), problem=_draft("problem"),
            goals=_draft("goals"), users=_draft("users"),
        ),
        features=generator.FeaturePlan(features=[generator.Feature(
            title="알림 채널 선택", description="앱 푸시나 문자로 알림을 보낸다.",
            evidence=[Evidence(quote=quote)],
        )]),
        technical=generator.TechnicalDecisionPlan(
            tech_scope=generator.TechScopeDraft(),
            decisions=generator.DecisionsDraft(),
        ),
    )
    index = generator.PlanningFactIndex(facts=[generator.PlanningFact(
        topic="알림 채널", status="unresolved", content="비용 확인이 필요하다.",
        evidence=[Evidence(quote=quote)], section_candidates=["features"],
    )])

    filtered = generator.filter_nonfinal_outputs(draft, index)

    assert filtered.features.features == []


def test_nonfinal_filter_restores_explicit_exclusion_decision_when_missing():
    quote = "외부 강사는 1차 범위에서 제외한다."
    draft = generator.WholePlanDraft(
        context=generator.ContextPlan(
            overview=_draft("overview"), problem=_draft("problem"),
            goals=_draft("goals"), users=_draft("users"),
        ),
        features=generator.FeaturePlan(),
        technical=generator.TechnicalDecisionPlan(
            tech_scope=generator.TechScopeDraft(),
            decisions=generator.DecisionsDraft(),
        ),
    )
    index = generator.PlanningFactIndex(facts=[generator.PlanningFact(
        topic="외부 강사", status="rejected", content="외부 강사는 1차 범위에서 제외한다.",
        evidence=[Evidence(quote=quote)], section_candidates=["users", "decisions"],
    )])

    filtered = generator.filter_nonfinal_outputs(draft, index)

    assert [item.content for item in filtered.technical.decisions.items] == [
        "외부 강사는 1차 범위에서 제외한다."
    ]


def test_render_features_removes_evidence_storage_as_product_feature():
    draft = generator.Feature(
        title="근거 문장 보존 적재",
        description="근거 문장을 RDS에 저장하고 원본은 오브젝트 스토리지에 보존한다.",
        evidence=[Evidence(quote=QUOTE_1)],
    )

    section = generator.render_features([draft], SOURCE)

    assert section.features == []
    assert section.is_incomplete


def test_very_long_generation_payload_uses_verified_fact_excerpts_only():
    index = generator.PlanningFactIndex(facts=[
        generator.PlanningFact(
            topic="기준 소스", status="confirmed", content="A몰을 사용한다.",
            evidence=[Evidence(quote=QUOTE_1)], section_candidates=["decisions"],
        ),
    ])

    payload = json.loads(
        generator.whole_plan_messages(SOURCE, index, include_full_source=False)[0]["content"]
    )

    assert payload["source_mode"] == "verified_fact_excerpts"
    assert payload["meeting_source_text"] == ""
    assert payload["planning_fact_index"]["facts"][0]["evidence"][0]["quote"] == QUOTE_1


def test_long_source_builds_chunk_indexes_in_order(monkeypatch):
    source = "첫 구간의 확정 내용입니다.\n\n둘째 구간의 미결정 내용입니다."
    monkeypatch.setattr(
        agent, "_split_source_for_index",
        lambda _source: ["첫 구간의 확정 내용입니다.", "둘째 구간의 미결정 내용입니다."],
    )

    def call(_system, messages, response_model, **_kwargs):
        assert response_model is generator.PlanningFactIndex
        text = messages[0]["content"]
        if "첫 구간" in text:
            return generator.PlanningFactIndex(facts=[
                generator.PlanningFact(
                    topic="범위", status="confirmed", content="첫 결정",
                    evidence=[Evidence(quote="첫 구간의 확정 내용입니다.")],
                    section_candidates=["decisions"], source_order=1,
                )
            ])
        return generator.PlanningFactIndex(facts=[
            generator.PlanningFact(
                topic="기준", status="unresolved", content="둘째 미결정",
                evidence=[Evidence(quote="둘째 구간의 미결정 내용입니다.")],
                section_candidates=["decisions"], source_order=1,
            )
        ])

    monkeypatch.setattr(agent, "_call", call)
    result = agent._build_planning_fact_index(source, "long-test")

    assert [(fact.status, fact.source_order) for fact in result.facts] == [
        ("confirmed", 1), ("unresolved", 2),
    ]


def test_render_technical_sections_groups_items_and_verifies_quotes():
    draft = generator.TechnicalDecisionPlan(
        tech_scope=generator.TechScopeDraft(groups=[
            generator.TechGroupDraft(
                title="기술 구성",
                items=[generator.CitedListItem(
                    text="분석 파이프라인을 자동화한다.",
                    evidence=[Evidence(quote="완전 자동화가 목표입니다.")],
                )],
            )
        ]),
        decisions=generator.DecisionsDraft(items=[
            generator.DecisionItemDraft(
                category="scope",
                content="A몰을 기준 상품 소스로 사용한다.",
                rationale="기준 데이터로 선택했다.",
                evidence=[Evidence(quote=QUOTE_1)],
            )
        ]),
    )

    tech, decisions = generator.render_technical_sections(draft, SOURCE)

    assert tech.groups[0].subtitle == "기술 구성"
    assert tech.evidence[0].quote == "완전 자동화가 목표입니다."
    assert decisions.items == [
        "[범위] A몰을 기준 상품 소스로 사용한다. (이유: 기준 데이터로 선택했다.)"
    ]
    assert decisions.evidence[0].quote == QUOTE_1


def test_render_features_keeps_item_evidence_and_marks_missing_quote():
    features = [
        generator.Feature(
            title="트렌드 분석",
            description="상품 반응을 이용해 트렌드를 분석한다.",
            evidence=[Evidence(quote=QUOTE_2)],
        ),
        generator.Feature(
            title="잘못된 기능",
            description="근거가 없는 기능이다.",
            evidence=[Evidence(quote="원문에 없는 문장")],
        ),
    ]

    result = generator.render_features(features, SOURCE)

    assert result.items == ["트렌드 분석", "잘못된 기능"]
    assert [item.quote for item in result.evidence] == [QUOTE_2]
    assert "'잘못된 기능' 기능의 작성 근거" in result.needs_input


def test_render_features_excludes_implementation_only_storage_design():
    features = [
        generator.Feature(
            title="원본 데이터 보관·저장소 분리",
            description="원본은 S3, 서비스 데이터는 RDS에 저장한다.",
            evidence=[Evidence(quote=QUOTE_1)],
        ),
        generator.Feature(
            title="원본 보존·근거 연결 저장",
            description="원본과 지표를 식별자로 연결한다.",
            evidence=[Evidence(quote=QUOTE_1)],
        ),
        generator.Feature(
            title="무신사 기반 학습 데이터 수집",
            description="학습용 상품 이미지를 수집한다.",
            evidence=[Evidence(quote=QUOTE_1)],
        ),
        generator.Feature(
            title="원본/가공 데이터 저장 분리",
            description="원본과 가공 데이터를 서로 다른 저장소에 저장한다.",
            evidence=[Evidence(quote=QUOTE_1)],
        ),
        generator.Feature(
            title="트렌드 분석",
            description="상품 반응으로 트렌드를 분석한다.",
            evidence=[Evidence(quote=QUOTE_2)],
        ),
    ]

    result = generator.render_features(features, SOURCE)

    assert result.items == ["트렌드 분석"]


def test_render_features_removes_tentative_sub_action_and_schema_sentence():
    source = (
        "자막이 없으면 음성 인식으로 자막을 만듭니다. "
        "오타들이 나길래 후처리를 한 번 해야 하나 싶었어요. "
        "대표 용어 테이블과 동의어 매핑 테이블을 ID로 연결합니다. "
        "수집 데이터는 대표 용어로 치환합니다."
    )
    features = [
        generator.Feature(
            title="자동 자막 생성 및 오탈자 보정",
            description=(
                "자막이 없으면 음성 인식으로 자막을 생성합니다. "
                "전사 오탈자는 후처리로 교정합니다."
            ),
            evidence=[
                Evidence(quote="자막이 없으면 음성 인식으로 자막을 만듭니다."),
                Evidence(quote="오타들이 나길래 후처리를 한 번 해야 하나 싶었어요."),
            ],
        ),
        generator.Feature(
            title="패션 용어 사전 정규화",
            description=(
                "대표 용어 ID와 동의어 테이블을 연결합니다. "
                "수집 데이터는 대표 용어로 치환합니다."
            ),
            evidence=[
                Evidence(quote="대표 용어 테이블과 동의어 매핑 테이블을 ID로 연결합니다."),
                Evidence(quote="수집 데이터는 대표 용어로 치환합니다."),
            ],
        ),
        generator.Feature(
            title="패션 이미지 스타일 자동 태깅",
            description=(
                "상품 이미지에 상위 스타일 태그를 자동 부여합니다. "
                "초기 학습은 CLIP계열 주클로 모델로 진행하고 고클립 대안도 검토합니다."
            ),
            evidence=[Evidence(quote="수집 데이터는 대표 용어로 치환합니다.")],
        ),
    ]

    result = generator.render_features(features, source)

    assert result.items == [
        "자동 자막 생성", "패션 용어 사전 정규화", "패션 이미지 스타일 자동 태깅",
    ]
    assert "후처리로 교정" not in result.content_html
    assert "테이블을 ID로 연결" not in result.content_html
    assert "대표 용어 ID와 동의어 테이블" not in result.content_html
    assert "수집 데이터는 대표 용어로 치환" in result.content_html
    assert "고클립 대안" not in result.content_html
    assert "상품 이미지에 상위 스타일 태그를 자동 부여" in result.content_html


def test_reconcile_uses_final_decisions_and_softens_pending_feature_claims():
    feature_section = generator.render_features([
        generator.Feature(
            title="상품 스냅샷 관리",
            description=(
                "신상품과 중고 가격을 수집합니다. "
                "신상품과 중고 데이터를 단일 스키마로 관리합니다."
            ),
            evidence=[Evidence(quote=QUOTE_1)],
            review_questions=["크림과 무신사 유즈드를 데이터 소스로 확정할까요?"],
        )
    ], SOURCE)
    decisions = generator.DecisionsDraft(
        items=[generator.DecisionItemDraft(
            category="scope",
            content="크림과 무신사 유즈드를 데이터 소스로 확정한다.",
            evidence=[Evidence(quote=QUOTE_1)],
        )],
        review_questions=["신상품과 중고 데이터 스키마를 단일 통합할지 분리할지 결정이 필요합니다."],
    )

    result = generator.reconcile_sections([feature_section], decisions)[0]

    assert result.features[0].description == "신상품과 중고 가격을 수집합니다."
    assert result.features[0].review_questions == []
    assert "크림과 무신사" not in result.content_html


def test_users_render_separates_confirmed_and_proposed_groups():
    draft = generator.UsersDraft(users=[
        generator.UserDraft(
            name="트렌드 분석가", description="데이터를 검토한다.", usage="",
            evidence=[Evidence(quote=QUOTE_2)], is_proposal=False,
        ),
        generator.UserDraft(
            name="브랜드 담당자", description="지표를 활용한다.", usage="",
            evidence=[Evidence(quote=QUOTE_2)], is_proposal=True,
        ),
    ])

    result = generator.render_section(draft, SOURCE, _spec("users"))

    assert "<strong>확인된 사용자</strong>" in result.content_html
    assert "<strong>제안 사용자</strong>" in result.content_html


def test_users_render_reclassifies_user_without_direct_role_evidence_as_proposed():
    draft = generator.UsersDraft(users=[
        generator.UserDraft(
            name="패션 MD", description="상품 지표를 활용한다.", usage="",
            evidence=[Evidence(quote=QUOTE_1)], is_proposal=False,
        ),
    ])

    result = generator.render_section(draft, SOURCE, _spec("users"))

    assert "<strong>제안 사용자</strong>" in result.content_html
    assert "패션 MD를 서비스 대상 사용자로 정의할지 확인이 필요합니다." in result.content_html


def test_reconcile_removes_confirmed_question_with_one_distinctive_topic_token():
    overview = generator.PlanSection(
        no=1, key="overview", title="프로젝트 개요", section_type="narrative",
        content_html="<p>개요</p>" + generator._review_html([
            "무신사를 기준 축으로 확정할까요?",
        ]),
        needs_input="무신사를 기준 축으로 확정할까요?",
    )
    decisions = generator.DecisionsDraft(items=[
        generator.DecisionItemDraft(
            category="data",
            content="무신사를 주요 데이터 소스로 채택한다.",
            evidence=[Evidence(quote=QUOTE_1)],
        ),
    ])

    result = generator.reconcile_sections([overview], decisions)[0]

    assert result.needs_input == ""
    assert "PM 확인 사항" not in result.content_html


def test_reconcile_moves_user_scope_question_to_users_section():
    overview = generator.PlanSection(
        no=1, key="overview", title="프로젝트 개요", section_type="narrative",
        content_html="<p>개요</p>" + generator._review_html([
            "외부 고객을 대상 사용자에 포함할까요?",
        ]),
        needs_input="외부 고객을 대상 사용자에 포함할까요?",
    )
    users = generator.PlanSection(
        no=4, key="users", title="대상 사용자", section_type="narrative",
        content_html="<p>제안 사용자</p>", needs_input="",
    )

    result = generator.reconcile_sections(
        [overview, users], generator.DecisionsDraft(),
    )

    assert result[0].needs_input == ""
    assert result[1].needs_input == "외부 고객을 대상 사용자에 포함할까요?"
    assert "외부 고객을 대상 사용자에 포함할까요?" in result[1].content_html


def test_users_render_does_not_repeat_individual_questions_when_group_question_exists():
    draft = generator.UsersDraft(
        users=[
            generator.UserDraft(
                name="브랜드 담당자", description="지표를 활용한다.", usage="",
                evidence=[Evidence(quote=QUOTE_1)], is_proposal=True,
            ),
            generator.UserDraft(
                name="리셀 담당자", description="가격을 확인한다.", usage="",
                evidence=[Evidence(quote=QUOTE_2)], is_proposal=True,
            ),
        ],
        review_questions=["외부 사용자 후보의 포함 여부와 우선순위를 확정할까요?"],
    )

    result = generator.render_section(draft, SOURCE, _spec("users"))

    assert result.needs_input.splitlines() == [
        "외부 사용자 후보의 포함 여부와 우선순위를 확정할까요?"
    ]


@pytest.mark.parametrize("key", ["overview", "problem", "goals", "users"])
def test_regeneration_uses_same_source_and_renderer(monkeypatch, key):
    def call(system, messages, response_model, **kwargs):
        assert response_model is generator.SECTION_MODELS[key]
        payload = json.loads(messages[-1]["content"])
        assert payload["structured"]["meeting_source_text"] == SOURCE
        return _draft(key)

    monkeypatch.setattr(agent, "_call", call)
    result = agent.regenerate_section({"plan_source_text": SOURCE}, key, "content", "문맥 반영")
    assert result.key == key
    assert len(result.evidence) == 2


def test_model_requires_all_four_sections():
    with pytest.raises(ValidationError):
        generator.ContextPlan(
            problem=_draft("problem"), goals=_draft("goals"), users=_draft("users"),
        )


def test_empty_users_are_incomplete_even_with_review_notes():
    draft = generator.UsersDraft(users=[], review_questions=["사용자 확인"])
    result = generator.render_section(draft, SOURCE, _spec("users"))
    assert result.is_incomplete
    assert "사용자 확인" in result.content_html


def test_goal_direction_text_is_preserved_verbatim():
    result = generator.render_section(_draft("goals"), SOURCE, _spec("goals"))
    assert "<strong>추진 목표:</strong> 처리 과정을 자동화한다." in result.content_html
    assert "누락이 아닌지" not in result.content_html


def test_overview_paragraph_rejects_implementation_detail():
    """
    1~2번 문단에 저장 구조·수집 주기 같은 구현 세부사항이 섞이면 즉시 거부한다.
    instructor가 이 ValidationError를 LLM에 재요청(reask) 메시지로 그대로
    돌려주므로, 메시지 자체가 "무엇이 왜 틀렸는지"를 설명해야 한다.
    """
    with pytest.raises(ValidationError, match="오브젝트 스토리지"):
        generator.CitedParagraph(
            text="원본은 오브젝트 스토리지에 보관하고 서비스 데이터만 DB에 적재한다.",
        )


def test_overview_paragraph_allows_clean_text():
    para = generator.CitedParagraph(text="상품과 콘텐츠 데이터를 연결해 트렌드를 분석한다.")
    assert "트렌드" in para.text


def test_core_goal_prompt_defines_outcome_instead_of_feature_list():
    prompt = generator.system_prompt()

    assert "무엇을 만든다" in prompt
    assert "기능 목록입니다" in prompt
    assert "일관되고 신뢰할 수 있는 트렌드 판단 근거" in prompt


@pytest.mark.parametrize("word,expected", [
    ("사장님", "을"),       # 받침 있음(ㅁ)
    ("직원(파트타임)", "을"),  # 받침 있음(ㄴ), 닫는 괄호는 건너뜀
    ("보호자", "를"),       # 받침 없음
    ("이용자", "를"),       # 받침 없음
    ("내부 분석가/기획자", "를"),  # 받침 없음(자)
    ("John", "를"),         # 한글 아님 → 받침 없음으로 간주
])
def test_josa_picks_batchim_correct_particle(word, expected):
    assert generator._josa(word, "을", "를") == expected

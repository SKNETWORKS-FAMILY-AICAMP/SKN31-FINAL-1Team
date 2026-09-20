"""원문 기반 1~4번 생성 경로. 실제 API 호출 없는 계약·조립 검증."""

import json

import pytest
from pydantic import ValidationError

from plan_draft import agent, context_writer
from plan_draft.schemas import SECTION_SPEC
from shared.schemas_base import Evidence


SOURCE = "상품은 A몰을 기준으로 합니다. 주목적은 트렌드 분석입니다. 완전 자동화가 목표입니다."
QUOTE_1 = "상품은 A몰을 기준으로 합니다."
QUOTE_2 = "주목적은 트렌드 분석입니다."


def _draft(key):
    """SOURCE에 실제로 있는 인용 2개를 물고 있는 섹션별 초안을 만듭니다."""
    evidence = [Evidence(quote=QUOTE_1), Evidence(quote=QUOTE_2)]

    if key == "overview":
        para = context_writer.CitedParagraph(
            text="상품 정보와 반응을 연결해 분석한다.", evidence=evidence,
        )
        empty = context_writer.CitedParagraph(text="")
        return context_writer.OverviewDraft(
            service_overview=para, data_scope=empty, current_and_future=empty,
        )
    if key == "problem":
        para = context_writer.CitedParagraph(
            text="상품 정보와 반응을 연결해 분석한다.", evidence=evidence,
        )
        empty = context_writer.CitedParagraph(text="")
        return context_writer.CoreGoalDraft(core_goal=para, approach=empty)
    if key == "goals":
        goal = context_writer.DetailedGoalDraft(
            title="분석 자동화", problem="수동으로 처리하고 있다.",
            direction="처리 과정을 자동화한다.", evidence=evidence,
        )
        return context_writer.GoalsDraft(goals=[goal])
    if key == "users":
        user = context_writer.UserDraft(
            name="사장님", description="상품 정보와 반응을 연결해 분석한다.",
            usage="", evidence=evidence, is_proposal=True,
        )
        return context_writer.UsersDraft(users=[user])
    raise ValueError(key)


def _spec(key):
    return next(s for s in SECTION_SPEC if s["key"] == key)


def test_render_keeps_multiple_quotes_and_marks_proposed_user():
    result = context_writer.render_section(_draft("users"), SOURCE, _spec("users"))
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
    user = context_writer.UserDraft(
        name="보호자", description="환자의 복약 상황을 함께 인지한다.",
        usage="", evidence=evidence, is_proposal=True,
    )
    draft = context_writer.UsersDraft(users=[user])
    result = context_writer.render_section(draft, SOURCE, _spec("users"))
    assert "보호자를 서비스 대상 사용자로 정의할지 확인이 필요합니다." in result.content_html
    assert "보호자을" not in result.content_html


def test_missing_quote_is_not_verified_and_html_is_escaped():
    para = context_writer.CitedParagraph(
        text="<script>test</script>",
        evidence=[Evidence(quote="원문에 없는 인용입니다.")],
    )
    empty = context_writer.CitedParagraph(text="")
    draft = context_writer.OverviewDraft(
        service_overview=para, data_scope=empty, current_and_future=empty,
        review_questions=["<권한 확인>"],
    )
    result = context_writer.render_section(draft, SOURCE, _spec("overview"))
    assert result.evidence == []
    assert "원문과 대조해 확인해 주세요" in result.content_html
    assert "<script>" not in result.content_html
    assert "&lt;권한 확인&gt;" in result.content_html


def test_generation_receives_source_without_legacy_limits(monkeypatch):
    def call(system, messages, response_model, **kwargs):
        assert len(messages) == 1
        if response_model is context_writer.ContextPlan:
            payload = json.loads(messages[0]["content"])
            assert payload["meeting_source_text"] == SOURCE
            return context_writer.ContextPlan(
                overview=_draft("overview"),
                problem=_draft("problem"),
                goals=_draft("goals"),
                users=_draft("users"),
            )
        assert response_model is context_writer.TechnicalDecisionPlan
        assert SOURCE in messages[0]["content"]
        return context_writer.TechnicalDecisionPlan(
            tech_scope=context_writer.TechScopeDraft(groups=[
                context_writer.TechGroupDraft(
                    title="데이터·저장 방침",
                    items=[context_writer.CitedListItem(
                        text="A몰을 기준 상품 소스로 사용한다.",
                        evidence=[Evidence(quote=QUOTE_1)],
                    )],
                )
            ]),
            decisions=context_writer.DecisionsDraft(items=[
                context_writer.DecisionItemDraft(
                    category="scope",
                    content="A몰을 기준 상품 소스로 사용한다.",
                    evidence=[Evidence(quote=QUOTE_1)],
                )
            ]),
        )

    monkeypatch.setattr(agent, "_call", call)
    result = agent.run({"plan_source_text": SOURCE, "project": {}, "requirements": {}}, "test")
    assert len(result.sections) == 7
    for item in result.sections[:4]:
        assert len(item.evidence) == 2
        assert not item.is_incomplete
    assert result.sections[2].items
    assert result.sections[4].key == "features"
    assert result.sections[5].evidence[0].quote == QUOTE_1
    assert result.sections[6].items == ["[범위] A몰을 기준 상품 소스로 사용한다."]


def test_render_technical_sections_groups_items_and_verifies_quotes():
    draft = context_writer.TechnicalDecisionPlan(
        tech_scope=context_writer.TechScopeDraft(groups=[
            context_writer.TechGroupDraft(
                title="기술 구성",
                items=[context_writer.CitedListItem(
                    text="분석 파이프라인을 자동화한다.",
                    evidence=[Evidence(quote="완전 자동화가 목표입니다.")],
                )],
            )
        ]),
        decisions=context_writer.DecisionsDraft(items=[
            context_writer.DecisionItemDraft(
                category="scope",
                content="A몰을 기준 상품 소스로 사용한다.",
                rationale="기준 데이터로 선택했다.",
                evidence=[Evidence(quote=QUOTE_1)],
            )
        ]),
    )

    tech, decisions = context_writer.render_technical_sections(draft, SOURCE)

    assert tech.groups[0].subtitle == "기술 구성"
    assert tech.evidence[0].quote == "완전 자동화가 목표입니다."
    assert decisions.items == [
        "[범위] A몰을 기준 상품 소스로 사용한다. (이유: 기준 데이터로 선택했다.)"
    ]
    assert decisions.evidence[0].quote == QUOTE_1


@pytest.mark.parametrize("key", ["overview", "problem", "goals", "users"])
def test_regeneration_uses_same_source_and_renderer(monkeypatch, key):
    def call(system, messages, response_model, **kwargs):
        assert response_model is context_writer.SECTION_MODELS[key]
        payload = json.loads(messages[-1]["content"])
        assert payload["structured"]["meeting_source_text"] == SOURCE
        return _draft(key)

    monkeypatch.setattr(agent, "_call", call)
    result = agent.regenerate_section({"plan_source_text": SOURCE}, key, "content", "문맥 반영")
    assert result.key == key
    assert len(result.evidence) == 2


def test_model_requires_all_four_sections():
    with pytest.raises(ValidationError):
        context_writer.ContextPlan(
            problem=_draft("problem"), goals=_draft("goals"), users=_draft("users"),
        )


def test_empty_users_are_incomplete_even_with_review_notes():
    draft = context_writer.UsersDraft(users=[], review_questions=["사용자 확인"])
    result = context_writer.render_section(draft, SOURCE, _spec("users"))
    assert result.is_incomplete
    assert "사용자 확인" in result.content_html


def test_goal_direction_text_is_preserved_verbatim():
    result = context_writer.render_section(_draft("goals"), SOURCE, _spec("goals"))
    assert "<strong>추진 목표:</strong> 처리 과정을 자동화한다." in result.content_html
    assert "누락이 아닌지" not in result.content_html


def test_overview_paragraph_rejects_implementation_detail():
    """
    1~2번 문단에 저장 구조·수집 주기 같은 구현 세부사항이 섞이면 즉시 거부한다.
    instructor가 이 ValidationError를 LLM에 재요청(reask) 메시지로 그대로
    돌려주므로, 메시지 자체가 "무엇이 왜 틀렸는지"를 설명해야 한다.
    """
    with pytest.raises(ValidationError, match="오브젝트 스토리지"):
        context_writer.CitedParagraph(
            text="원본은 오브젝트 스토리지에 보관하고 서비스 데이터만 DB에 적재한다.",
        )


def test_overview_paragraph_allows_clean_text():
    para = context_writer.CitedParagraph(text="상품과 콘텐츠 데이터를 연결해 트렌드를 분석한다.")
    assert "트렌드" in para.text


def test_core_goal_prompt_defines_outcome_instead_of_feature_list():
    prompt = context_writer.system_prompt()

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
    assert context_writer._josa(word, "을", "를") == expected

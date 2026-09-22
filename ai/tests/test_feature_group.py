"""
Feature.group 표시(render_features) 테스트.

2026-09-17: 이 파일이 테스트하던 decide_feature_groups·build_features는
list_builder.py에서 삭제했습니다 — 2026-09-15에 5번(주요 기능) 작성
자체가 LLM 직접 작성 방식으로 바뀌면서 두 함수 모두 프로덕션 어디서도
호출되지 않는 죽은 코드가 됐습니다(agent.py는 result.features를 그대로
쓰고 group은 항상 "mvp"로 고정됩니다 — plan_generation.yaml
features_rules 참고). mvp/integration을 실제로 재판정하는 코드는 지금
없습니다.

render_features는 Feature 목록을 group별로 나눠 보여주는 순수 렌더링
함수라 이 변경과 무관하게 그대로 유지합니다 — 아래 테스트는 그 렌더링
동작만 검증합니다(입력 Feature 객체는 직접 구성한 것이며, group 판정
로직과는 별개입니다).
"""

from plan_draft.feature_renderer import render_features
from plan_draft.schemas import Feature


def test_renderer_adds_headings_when_both_groups_exist():
    html = render_features(
        [
            Feature(title="등록", description="설명1", group="mvp"),
            Feature(title="조회", description="설명2", group="mvp"),
            Feature(title="연동", description="설명3", group="integration"),
        ]
    )
    assert "MVP 기능 2개" in html
    assert "별도 연동 1건" in html
    assert html.index("MVP 기능 2개") < html.index("별도 연동 1건")


def test_renderer_omits_headings_when_single_group():
    """한 종류뿐이면 회의에 없는 구분을 화면이 주장하지 않습니다."""
    html = render_features(
        [
            Feature(title="등록", description="설명1", group="mvp"),
            Feature(title="조회", description="설명2", group="mvp"),
        ]
    )
    assert "MVP 기능" not in html
    assert "별도 연동" not in html
    assert "등록" in html and "조회" in html


def test_renderer_escapes_html_in_titles():
    html = render_features(
        [Feature(title="<b>등록</b>", description="a & b", group="mvp")]
    )
    assert "<b>등록</b>" not in html
    assert "&lt;b&gt;" in html
    assert "a &amp; b" in html


def test_renderer_handles_empty_list():
    assert render_features([]) == ""

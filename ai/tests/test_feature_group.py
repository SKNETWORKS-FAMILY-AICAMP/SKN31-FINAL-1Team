"""
Feature.group 판정과 표시 테스트.

group은 LLM이 정하지 않고 코드가 근거로 판정합니다.
판정 기준은 "여러 기능이 같은 quote를 공유하는가"뿐입니다.
LLM을 호출하지 않으므로 이 파일의 테스트는 전부 결정적입니다.
"""

from plan_draft.feature_renderer import render_features
from plan_draft.list_builder import (
    build_features,
    decide_feature_groups,
)
from plan_draft.schemas import Feature


def _func(content, name, quote):
    return {
        "content": content,
        "feature_name": name,
        "evidence": {"quote": quote},
        "evidence_status": "verified",
    }


def _structured(items):
    return {
        "requirements": {"functional": items},
        "decisions": [],
    }


# ── decide_feature_groups ────────────────────────────────


def test_shared_quote_marks_features_as_mvp():
    """여러 기능이 같은 문장을 근거로 쓰면 확정 목록입니다."""
    groups = decide_feature_groups(
        {"열거문장": {"등록", "조회", "알림"}}
    )
    assert groups == {
        "등록": "mvp",
        "조회": "mvp",
        "알림": "mvp",
    }


def test_own_quote_only_marks_feature_as_integration():
    """자기 근거만 가진 기능은 목록과 별개로 확정된 것입니다."""
    groups = decide_feature_groups(
        {
            "열거문장": {"등록", "조회"},
            "연동문장": {"외부 연동"},
        }
    )
    assert groups["등록"] == "mvp"
    assert groups["조회"] == "mvp"
    assert groups["외부 연동"] == "integration"


def test_no_shared_quote_keeps_everything_mvp():
    """열거 문장이 없으면 판정 근거가 없으므로 기본값을 씁니다.

    여기서 전부 integration으로 두면 확정 기능이 하나도 남지 않습니다.
    """
    groups = decide_feature_groups(
        {
            "문장1": {"등록"},
            "문장2": {"조회"},
        }
    )
    assert set(groups.values()) == {"mvp"}


def test_empty_input_returns_empty_mapping():
    assert decide_feature_groups({}) == {}


# ── build_features 연동 ──────────────────────────────────


def test_build_features_assigns_group_from_evidence():
    """열거 문장에 든 기능과 별도 확정된 기능이 갈립니다."""
    listed = "제공 기능은 입출고 등록과 재고 조회로 확정한다."
    features = build_features(
        _structured(
            [
                _func("입출고 등록 기능을 제공한다", "입출고 등록", listed),
                _func("재고 조회 기능을 제공한다", "재고 조회", listed),
                _func(
                    "외부 시스템 연동은 A사만 지원한다",
                    "외부 연동",
                    "외부 시스템 연동은 A사만 지원한다.",
                ),
            ]
        )
    )
    by_title = {f.title: f.group for f in features}
    assert by_title["입출고 등록"] == "mvp"
    assert by_title["재고 조회"] == "mvp"
    assert by_title["외부 연동"] == "integration"


def test_build_features_defaults_to_mvp_without_list_sentence():
    features = build_features(
        _structured(
            [
                _func("입출고 등록 기능", "입출고 등록", "입출고 등록 기능을 제공한다."),
                _func("재고 조회 기능", "재고 조회", "재고 조회 기능을 제공한다."),
            ]
        )
    )
    assert {f.group for f in features} == {"mvp"}


# ── render_features ──────────────────────────────────────


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
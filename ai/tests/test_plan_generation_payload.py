"""
노드 2 입력과 코드 기반 주요 기능 조립 테스트.

실제 OpenAI API와 DB는 호출하지 않습니다.
"""

from plan_draft import agent as plan_agent
from plan_draft.list_builder import (
    build_features,
    collect_feature_evidence,
)
from plan_draft.prompt_loader import (
    build_plan_system_prompt,
    load_plan_template,
)
from plan_draft.prompts import (
    _build_generation_payload,
)
from plan_draft.schemas import PlanSections


def _evidence(quote: str) -> dict:
    return {"quote": quote}


def _functional(
    content: str,
    feature_name: str | None,
    *,
    status: str = "verified",
    quote: str | None = None,
) -> dict:
    return {
        "content": content,
        "feature_name": feature_name,
        "evidence": _evidence(quote or content),
        "evidence_status": status,
    }


def test_generation_payload_only_exposes_narrative_sources():
    project = {
        "name": "리테일링크",
        "problem_items": [],
        "goals": [],
    }
    users = [{"type": "소상공인 사장"}]

    payload = _build_generation_payload(
        {
            "project": project,
            "users": users,
            "requirements": {
                "functional": [
                    _functional(
                        "바코드 등록을 제공한다.",
                        "바코드 등록",
                    )
                ]
            },
            "decisions": [
                {
                    "category": "feature",
                    "content": "바코드 방식을 확정한다.",
                }
            ],
        }
    )

    assert payload == {
        "project": project,
        "users": users,
    }


def test_plan_prompt_does_not_ask_llm_to_generate_features():
    template = load_plan_template()
    prompt = build_plan_system_prompt()

    assert template["metadata"]["version"] == "2.2"
    assert template["output_contract"]["root_fields"] == [
        "sections",
        "goals",
    ]
    assert "feature_rules" not in template
    assert "주요 기능 작성 규칙" not in prompt
    assert "requirements.functional과 decisions는 목표 작성에 사용하지 않습니다" in prompt


def test_build_features_groups_verified_contents():
    barcode_quote = (
        "바코드 스캔은 BarcodeDetector 방식으로 구현하고 "
        "iOS에서는 ZXing 폴백을 사용한다."
    )
    order_quote = (
        "최근 4주 평균 판매량 기반 추천 수량 계산으로 대체한다."
    )
    pos_quote = (
        "POS 연동은 A사 API 1곳만 MVP에 포함하고 "
        "나머지는 2차 개발로 이관한다."
    )

    structured = {
        "requirements": {
            "functional": [
                _functional(
                    "바코드 입출고 등록 기능을 제공한다.",
                    "바코드 입출고 등록",
                ),
                _functional(
                    "바코드 스캔은 웹 카메라 API(BarcodeDetector) 방식으로 구현한다.",
                    "바코드 입출고 등록",
                    quote=barcode_quote,
                ),
                _functional(
                    "iOS 사파리 대응을 위한 ZXing 폴백을 필수로 포함한다.",
                    "바코드 입출고 등록",
                    quote=barcode_quote,
                ),
                _functional(
                    "발주서 자동 생성 기능을 제공한다.",
                    "발주서 자동 생성",
                ),
                _functional(
                    "최근 4주 평균 판매량 기반 추천 수량 계산을 제공한다.",
                    "발주서 자동 생성",
                    quote=order_quote,
                ),
                _functional(
                    "POS 연동은 A사 API 1곳만 포함한다.",
                    "POS 연동",
                    quote=pos_quote,
                ),
                _functional(
                    "거래 내역을 실시간 동기화한다.",
                    "POS 연동",
                    status="unverified",
                ),
            ]
        },
        "decisions": [
            {
                "category": "feature",
                "content": barcode_quote,
                "evidence": _evidence(barcode_quote),
                "evidence_status": "verified",
            },
            {
                "category": "scope",
                "content": (
                    "매출 예측 기능은 MVP에서 제외하고, "
                    "최근 4주 평균 판매량 기반 추천 수량 계산으로 대체한다."
                ),
                "evidence": _evidence(order_quote),
                "evidence_status": "verified",
            },
            {
                "category": "scope",
                "content": pos_quote,
                "evidence": _evidence(pos_quote),
                "evidence_status": "verified",
            },
        ],
    }

    features = build_features(structured)
    features_by_title = {
        feature.title: feature
        for feature in features
    }

    assert list(features_by_title) == [
        "바코드 입출고 등록",
        "발주서 자동 생성",
        "POS 연동",
    ]

    barcode = features_by_title[
        "바코드 입출고 등록"
    ].description
    assert "BarcodeDetector" in barcode
    assert "ZXing" in barcode
    assert "iOS" in barcode
    assert "기능을 제공한다" not in barcode

    order = features_by_title[
        "발주서 자동 생성"
    ].description
    assert "최근 4주" in order
    assert "평균 판매량" in order
    assert "추천 수량" in order
    assert "매출 예측 기능은 MVP에서 제외" in order

    pos = features_by_title["POS 연동"].description
    assert "A사 API 1곳" in pos
    assert "2차 개발로 이관" in pos
    assert "실시간 동기화" not in pos
    assert "거래 내역" not in pos


def test_build_features_preserves_mixed_null_items():
    features = build_features(
        {
            "requirements": {
                "functional": [
                    _functional(
                        "문의 등록 기능을 제공한다.",
                        "문의 등록",
                    ),
                    _functional(
                        "첨부파일은 최대 3개까지 허용한다.",
                        None,
                    ),
                ]
            }
        }
    )

    assert [feature.title for feature in features] == [
        "문의 등록",
        "기타 기능 요구사항",
    ]
    assert (
        "첨부파일은 최대 3개까지 허용한다."
        in features[1].description
    )


def test_build_features_preserves_legacy_functional_items():
    features = build_features(
        {
            "requirements": {
                "functional": [
                    _functional(
                        "구형 기능 요구사항을 제공한다.",
                        None,
                    )
                ]
            }
        }
    )

    assert len(features) == 1
    assert features[0].title == "기타 기능 요구사항"
    assert "구형 기능 요구사항" in features[0].description


def test_build_features_uses_verified_feature_decision_fallback():
    features = build_features(
        {
            "requirements": {"functional": []},
            "decisions": [
                {
                    "category": "feature",
                    "content": "긴급 문의 알림을 제공한다.",
                    "evidence": _evidence(
                        "긴급 문의 알림을 제공한다."
                    ),
                    "evidence_status": "verified",
                },
                {
                    "category": "feature",
                    "content": "거래 내역을 저장한다.",
                    "evidence": _evidence(
                        "원문에 없는 내용"
                    ),
                    "evidence_status": "unverified",
                },
            ],
        }
    )

    assert len(features) == 1
    assert features[0].title == "확정 기능"
    assert "긴급 문의 알림" in features[0].description
    assert "거래 내역" not in features[0].description


def test_feature_evidence_matches_verified_feature_sources():
    structured = {
        "requirements": {
            "functional": [
                _functional(
                    "확인된 기능을 제공한다.",
                    "확인된 기능",
                ),
                _functional(
                    "근거 없는 기능을 제공한다.",
                    "근거 없는 기능",
                    status="unverified",
                ),
            ]
        }
    }

    evidence = collect_feature_evidence(structured)

    assert [item.quote for item in evidence] == [
        "확인된 기능을 제공한다."
    ]


def test_regenerate_section_uses_defined_system_prompt(
    monkeypatch,
):
    captured = {}

    def fake_call(
        system,
        messages,
        response_model,
        context="",
    ):
        captured["system"] = system
        captured["messages"] = messages
        captured["response_model"] = response_model
        captured["context"] = context

        return PlanSections(
            sections=[
                {
                    "key": "overview",
                    "content_html": "<p>수정된 개요</p>",
                    "evidence": [],
                }
            ],
            goals=[],
        )

    monkeypatch.setattr(
        plan_agent,
        "_call",
        fake_call,
    )

    section = plan_agent.regenerate_section(
        structured={
            "project": {
                "name": "리테일링크",
                "background": "재고 관리 서비스",
            }
        },
        section_key="overview",
        reject_type="내용 부족",
        comment="프로젝트 배경을 보완해 주세요.",
    )

    expected_system = (
        plan_agent.build_system_prompt()
        + "\n\n"
        + plan_agent.REGENERATE_PROMPT
    )

    assert captured["system"] == expected_system
    assert captured["response_model"] is PlanSections
    assert section.key == "overview"
    assert section.content_html == "<p>수정된 개요</p>"


def test_regenerate_section_rejects_code_built_features(
    monkeypatch,
):
    def fail_call(*args, **kwargs):
        raise AssertionError(
            "주요 기능은 LLM을 호출하면 안 됩니다."
        )

    monkeypatch.setattr(
        plan_agent,
        "_call",
        fail_call,
    )

    try:
        plan_agent.regenerate_section(
            structured={},
            section_key="features",
            reject_type="내용 부족",
            comment="기능을 보완해 주세요.",
        )
    except ValueError as error:
        assert "재생성 대상이 아닙니다" in str(error)
    else:
        raise AssertionError(
            "features 재생성이 차단되지 않았습니다."
        )

"""
노드 2 기획서 생성 입력과 feature_name 그룹화 규칙 테스트.

실제 OpenAI API와 DB는 호출하지 않습니다.
"""

from plan_draft.list_builder import (
    build_features,
)
from plan_draft.prompt_loader import (
    build_plan_system_prompt,
)
from plan_draft.prompts import (
    _build_generation_payload,
)
from plan_draft.schemas import Feature


def _evidence(quote: str) -> dict:
    return {
        "quote": quote,
    }


def test_generation_payload_preserves_feature_name():
    functional = [
        {
            "content": "바코드 입출고 등록 기능을 제공한다.",
            "feature_name": "바코드 입출고 등록",
            "evidence": _evidence(
                "바코드 입출고 등록 기능을 제공한다."
            ),
            "evidence_status": "verified",
        },
        {
            "content": (
                "BarcodeDetector 방식과 "
                "ZXing 폴백을 사용한다."
            ),
            "feature_name": "바코드 입출고 등록",
            "evidence": _evidence(
                "BarcodeDetector 방식과 ZXing 폴백을 사용한다."
            ),
            "evidence_status": "verified",
        },
        {
            "content": (
                "최근 4주 평균 판매량으로 "
                "추천 수량을 계산한다."
            ),
            "feature_name": "발주서 자동 생성",
            "evidence": _evidence(
                "최근 4주 평균 판매량으로 추천 수량을 계산한다."
            ),
            "evidence_status": "verified",
        },
    ]

    payload = _build_generation_payload(
        {
            "requirements": {
                "functional": functional,
            },
        }
    )

    actual = payload["requirements"]["functional"]

    assert actual == functional
    assert [
        item["feature_name"]
        for item in actual
    ] == [
        "바코드 입출고 등록",
        "바코드 입출고 등록",
        "발주서 자동 생성",
    ]


def test_generation_payload_separates_scope_decisions():
    feature_decision = {
        "category": "feature",
        "content": "바코드 스캔 방식을 확정한다.",
        "evidence": _evidence(
            "바코드 스캔 방식을 확정한다."
        ),
        "evidence_status": "verified",
    }

    scope_decision = {
        "category": "scope",
        "content": (
            "MVP 기능 6개와 "
            "A사 POS 연동을 포함한다."
        ),
        "evidence": _evidence(
            "MVP 기능 6개와 A사 POS 연동을 포함한다."
        ),
        "evidence_status": "verified",
    }

    tech_decision = {
        "category": "tech",
        "content": "백엔드는 FastAPI를 사용한다.",
        "evidence": _evidence(
            "백엔드는 FastAPI를 사용한다."
        ),
        "evidence_status": "verified",
    }

    payload = _build_generation_payload(
        {
            "decisions": [
                feature_decision,
                scope_decision,
                tech_decision,
            ],
        }
    )

    assert payload["decisions"] == [
        feature_decision,
    ]
    assert payload["scope_decisions"] == [
        scope_decision,
    ]
    assert tech_decision not in payload["decisions"]
    assert tech_decision not in payload["scope_decisions"]


def test_plan_prompt_uses_structured_feature_grouping():
    prompt = build_plan_system_prompt()

    assert "feature_name" in prompt
    assert "scope_decisions" in prompt
    assert (
        "같은 feature_name을 가진 항목들은 "
        "정확히 하나의 주요 기능으로 출력합니다."
        in prompt
    )
    assert (
        "같은 feature_name 그룹에 속한 "
        "모든 verified content"
        in prompt
    )

def test_build_features_groups_verified_contents():
    structured = {
        "requirements": {
            "functional": [
                {
                    "content": (
                        "바코드 입출고 등록 기능을 제공한다."
                    ),
                    "feature_name": "바코드 입출고 등록",
                    "evidence": _evidence(
                        "바코드 입출고 등록 기능을 제공한다."
                    ),
                    "evidence_status": "verified",
                },
                {
                    "content": (
                        "바코드 스캔은 웹 카메라 API"
                        "(BarcodeDetector) 방식으로 구현한다."
                    ),
                    "feature_name": "바코드 입출고 등록",
                    "evidence": _evidence(
                        "BarcodeDetector 방식으로 구현한다."
                    ),
                    "evidence_status": "verified",
                },
                {
                    "content": (
                        "iOS 사파리 대응을 위한 ZXing 폴백을 "
                        "필수로 포함한다."
                    ),
                    "feature_name": "바코드 입출고 등록",
                    "evidence": _evidence(
                        "ZXing 폴백을 필수로 포함한다."
                    ),
                    "evidence_status": "verified",
                },
                {
                    "content": (
                        "발주서 자동 생성 기능을 제공한다."
                    ),
                    "feature_name": "발주서 자동 생성",
                    "evidence": _evidence(
                        "발주서 자동 생성 기능을 제공한다."
                    ),
                    "evidence_status": "verified",
                },
                {
                    "content": (
                        "최근 4주 평균 판매량 기반 "
                        "추천 수량 계산을 제공한다."
                    ),
                    "feature_name": "발주서 자동 생성",
                    "evidence": _evidence(
                        "최근 4주 평균 판매량 기반 "
                        "추천 수량 계산을 제공한다."
                    ),
                    "evidence_status": "verified",
                },
                {
                    "content": (
                        "POS 연동은 A사 API 1곳만 포함한다."
                    ),
                    "feature_name": "POS 연동",
                    "evidence": _evidence(
                        "POS 연동은 A사 API 1곳만 포함한다."
                    ),
                    "evidence_status": "verified",
                },
                {
                    "content": (
                        "거래 내역을 실시간 동기화한다."
                    ),
                    "feature_name": "POS 연동",
                    "evidence": _evidence(
                        "원문에 없는 근거"
                    ),
                    "evidence_status": "unverified",
                },
            ],
        },
    }

    generated_features = [
        Feature(
            title="바코드 입출고 등록",
            description=(
                "거래 내역을 실시간 동기화한다."
            ),
        ),
        Feature(
            title="발주서 자동 생성",
            description="발주서를 자동 생성한다.",
        ),
    ]

    features = build_features(
        structured,
        generated_features=generated_features,
    )

    assert [
        feature.title
        for feature in features
    ] == [
        "바코드 입출고 등록",
        "발주서 자동 생성",
        "POS 연동",
    ]

    features_by_title = {
        feature.title: feature
        for feature in features
    }

    barcode_description = (
        features_by_title[
            "바코드 입출고 등록"
        ].description
    )

    assert "BarcodeDetector" in barcode_description
    assert "ZXing" in barcode_description
    assert "iOS" in barcode_description

    order_description = (
        features_by_title[
            "발주서 자동 생성"
        ].description
    )

    assert "최근 4주" in order_description
    assert "평균 판매량" in order_description
    assert "추천 수량" in order_description

    pos_description = (
        features_by_title[
            "POS 연동"
        ].description
    )

    assert "A사 API 1곳" in pos_description
    assert "실시간 동기화" not in pos_description
    assert "거래 내역" not in pos_description


def test_build_features_uses_llm_fallback_without_feature_name():
    generated_features = [
        Feature(
            title="기존 기능",
            description="기존 LLM 생성 설명이다.",
        ),
    ]

    features = build_features(
        {
            "requirements": {
                "functional": [
                    {
                        "content": "구형 기능 요구사항",
                        "feature_name": None,
                        "evidence": _evidence(
                            "구형 기능 요구사항"
                        ),
                        "evidence_status": "verified",
                    },
                ],
            },
        },
        generated_features=generated_features,
    )

    assert features == generated_features
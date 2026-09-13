"""
기획서 목록형 섹션의 근거 연결 테스트.

6번 기술 스택 및 제약사항과
7번 최종 결정사항의 근거가 서로 섞이지 않는지 검증합니다.
"""

from plan_draft.list_builder import (
    build_decisions,
    build_tech_scope,
)


def _structured_data() -> dict:
    return {
        "requirements": {
            "technical": [
                {
                    "content": "백엔드는 Django를 사용한다.",
                    "evidence": {
                        "quote": "백엔드는 Django를 사용합니다."
                    },
                    "evidence_status": "verified",
                },
                {
                    "content": "데이터베이스는 MySQL을 사용한다.",
                    "evidence": {
                        "quote": "백엔드는 Django를 사용하고 데이터베이스는 MySQL을 사용합니다."
                    },
                    "evidence_status": "verified",
                },
                {
                    "content": "Django와 MySQL을 사용한다.",
                    "evidence": {
                        "quote": "백엔드는 Django를 사용하고 데이터베이스는 MySQL을 사용합니다."
                    },
                    "evidence_status": "verified",
                },
            ],
            "non_functional": [
                {
                    "content": "조회 화면은 3초 이내 표시한다.",
                    "evidence": {
                        "quote": "조회 화면은 3초 이내에 표시되어야 합니다."
                    },
                    "evidence_status": "verified",
                }
            ],
            "data": [
                {
                    "content": "최근 4주 판매량을 사용한다.",
                    "evidence": {
                        "quote": "최근 4주 판매량을 사용합니다."
                    },
                    "evidence_status": "verified",
                }
            ],
        },
        "constraints": [
            {
                "type": "일정",
                "content": "개발 기간은 10월까지다.",
                "evidence": {
                    "quote": "개발 기간은 10월까지입니다."
                },
                "evidence_status": "verified",
            }
        ],
        "decisions": [
            {
                "category": "feature",
                "content": "재고 알림을 제공한다.",
                "evidence": {
                    "quote": "재고 알림을 제공하기로 했습니다."
                },
                "evidence_status": "verified",
            },
            {
                "category": "scope",
                "content": "B사 POS는 2차 개발로 이관한다.",
                "evidence": {
                    "quote": "B사 POS는 2차 개발로 이관하기로 했습니다."
                },
                "evidence_status": "verified",
            },
        ],
    }


def test_tech_scope_does_not_use_feature_decision_evidence():
    structured = _structured_data()

    section = build_tech_scope(structured)

    quotes = [
        evidence.quote
        for evidence in section.evidence
    ]

    assert "백엔드는 Django를 사용합니다." in quotes
    assert "조회 화면은 3초 이내에 표시되어야 합니다." in quotes
    assert "최근 4주 판매량을 사용합니다." in quotes
    assert "개발 기간은 10월까지입니다." in quotes
    assert "B사 POS는 2차 개발로 이관하기로 했습니다." not in quotes

    # 기능 결정 근거가 6번 섹션에 섞이면 안 됩니다.
    assert "재고 알림을 제공하기로 했습니다." not in quotes


def test_decision_section_uses_decision_evidence():
    structured = _structured_data()

    section = build_decisions(structured)

    quotes = [
        evidence.quote
        for evidence in section.evidence
    ]

    assert quotes == [
        "재고 알림을 제공하기로 했습니다.",
        "B사 POS는 2차 개발로 이관하기로 했습니다.",
    ]


def test_tech_scope_removes_duplicate_evidence():
    structured = _structured_data()

    section = build_tech_scope(structured)

    quotes = [
        evidence.quote
        for evidence in section.evidence
    ]

    duplicated_quote = (
        "백엔드는 Django를 사용하고 "
        "데이터베이스는 MySQL을 사용합니다."
    )

    assert quotes.count(duplicated_quote) == 1

def test_feature_evidence_prefers_functional_and_falls_back_to_decision():
        """
        주요 기능은 기능 요구사항의 근거를 우선 사용합니다.
    
        기능 요구사항이 없을 때는 기능 결정사항의 근거를
        예비 근거로 사용합니다.
        """
        from plan_draft.list_builder import collect_feature_evidence
    
        structured_with_functional = {
            "requirements": {
                "functional": [
                    {
                        "content": "긴급 문의 알림을 제공한다.",
                        "evidence": {
                            "quote": (
                                "긴급 문의가 접수되면 "
                                "담당자에게 알림을 제공합니다."
                            )
                        },
                        "evidence_status": "verified",
                    }
                ]
            },
            "decisions": [
                {
                    "category": "feature",
                    "content": "긴급 문의 알림을 제공하기로 했다.",
                    "evidence": {
                        "quote": (
                            "긴급 문의가 접수되면 담당자에게 "
                            "알림을 제공하기로 했습니다."
                        )
                    },
                    "evidence_status": "verified",
                }
            ],
        }
    
        functional_result = collect_feature_evidence(
            structured_with_functional
        )
    
        assert len(functional_result) == 1
        assert functional_result[0].quote == (
            "긴급 문의가 접수되면 담당자에게 알림을 제공합니다."
        )
    
        structured_without_functional = {
            "requirements": {
                "functional": [],
            },
            "decisions": [
                {
                    "category": "feature",
                    "content": "긴급 문의 알림을 제공하기로 했다.",
                    "evidence": {
                        "quote": (
                            "긴급 문의가 접수되면 담당자에게 "
                            "알림을 제공하기로 했습니다."
                        )
                    },
                    "evidence_status": "verified",
                }
            ],
        }
    
        fallback_result = collect_feature_evidence(
            structured_without_functional
        )
    
        assert len(fallback_result) == 1
        assert fallback_result[0].quote == (
            "긴급 문의가 접수되면 담당자에게 "
            "알림을 제공하기로 했습니다."
        )

def test_core_goal_evidence_prefers_extracted_goals():
    """
    핵심 목표는 노드 1에서 추출한 목표 근거를 우선 사용합니다.

    목표가 존재할 때 배경, 전체 문제, 개별 문제와 기능 근거를
    모두 표시하지 않는지 검증합니다.
    """
    from plan_draft.list_builder import collect_core_goal_evidence

    structured = {
        "project": {
            "background": "여러 채널의 문의를 수기로 관리한다.",
            "background_evidence": {
                "quote": "여러 채널의 문의를 수기로 관리하고 있습니다."
            },
            "background_evidence_status": "verified",
            "problem": "문의 누락과 중복 응답이 발생한다.",
            "problem_evidence": {
                "quote": "문의 누락과 중복 응답이 발생하고 있습니다."
            },
            "problem_evidence_status": "verified",
            "problem_items": [
                {
                    "content": "긴급 문의가 누락된다.",
                    "evidence": {
                        "quote": "긴급 문의가 담당자에게 전달되지 않습니다."
                    },
                    "evidence_status": "verified",
                }
            ],
            "goals": [
                {
                    "content": "문의 누락과 중복 응답을 줄인다.",
                    "evidence": {
                        "quote": (
                            "여러 채널의 고객 문의를 한곳에서 관리하여 "
                            "문의 누락과 중복 응답을 줄입니다."
                        )
                    },
                    "evidence_status": "verified",
                },
                {
                    "content": "문의 처리 이력을 확인할 수 있게 한다.",
                    "evidence": {
                        "quote": (
                            "문의 상태 변경 이력을 저장하여 "
                            "처리 과정을 확인할 수 있게 합니다."
                        )
                    },
                    "evidence_status": "verified",
                },
            ],
        },
        "requirements": {
            "functional": [
                {
                    "content": "긴급 문의 알림을 제공한다.",
                    "evidence": {
                        "quote": "긴급 문의 알림을 제공합니다."
                    },
                    "evidence_status": "verified",
                }
            ]
        },
    }

    evidence = collect_core_goal_evidence(structured)
    quotes = [item.quote for item in evidence]

    assert quotes == [
        (
            "여러 채널의 고객 문의를 한곳에서 관리하여 "
            "문의 누락과 중복 응답을 줄입니다."
        ),
        (
            "문의 상태 변경 이력을 저장하여 "
            "처리 과정을 확인할 수 있게 합니다."
        ),
    ]

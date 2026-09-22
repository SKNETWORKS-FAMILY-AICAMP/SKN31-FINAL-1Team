"""
기획서 목록형 섹션의 근거 연결 테스트.

6번 기술 스택 및 제약사항과
7번 최종 결정사항의 근거가 서로 섞이지 않는지 검증합니다.
"""

from plan_draft.list_builder import (
    build_decisions,
    build_tech_scope,
    build_user_citation_sources,
    collect_source_evidence,
    collect_user_enrichment_evidence,
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


def test_decision_section_excludes_evidence_for_hidden_overstated_decision():
    structured = _structured_data()
    structured["decisions"][0]["context_flag"] = (
        "근거보다 과도하게 확정적으로 서술 — 제안 수준"
    )

    section = build_decisions(structured)
    quotes = [evidence.quote for evidence in section.evidence]

    assert "재고 알림을 제공하기로 했습니다." not in quotes
    assert quotes == ["B사 POS는 2차 개발로 이관하기로 했습니다."]


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


# ─────────────────────────────────────────────────────────────
# 2026-09-17 추가 — background_evidence_extra
#
# "프로젝트 개요" 화면의 근거자료가 항상 1개(background_evidence)로만
# 나와 신뢰하기 어렵다는 문제를 고치기 위해 meeting_analysis.schemas에
# 추가한 필드입니다. plan_draft는 원본 회의록에 접근할 수 없어 새 quote를
# 직접 검증할 수 없으므로, 이미 노드①이 검증해둔 값을 그대로 이어받아
# 노출하는지만 확인합니다.
# ─────────────────────────────────────────────────────────────


def test_background_evidence_extra가_overview_근거에_추가된다():
    structured = {
        "project": {
            "name": "리테일링크",
            "background": "종합된 배경 문장",
            "background_evidence": {"quote": "핵심 근거 문장"},
            "background_evidence_status": "verified",
            "background_evidence_extra": [
                {"quote": "추가 근거 문장 1"},
                {"quote": "추가 근거 문장 2"},
            ],
            "background_evidence_extra_status": ["verified", "unverified"],
        }
    }

    evidence = collect_source_evidence(
        structured, ["project.name", "project.background"]
    )
    by_quote = {item.quote: item.status for item in evidence}

    assert by_quote["핵심 근거 문장"] == "verified"
    assert by_quote["추가 근거 문장 1"] == "verified"
    assert by_quote["추가 근거 문장 2"] == "unverified"
    assert len(evidence) == 3


def test_background_evidence_extra가_없으면_기존과_동일하게_1개다():
    """필드가 아예 없는 옛 구조화 결과도 그대로 동작해야 합니다(하위 호환)."""
    structured = {
        "project": {
            "name": "리테일링크",
            "background": "배경 문장",
            "background_evidence": {"quote": "핵심 근거 문장"},
            "background_evidence_status": "verified",
        }
    }

    evidence = collect_source_evidence(
        structured, ["project.name", "project.background"]
    )

    assert len(evidence) == 1
    assert evidence[0].quote == "핵심 근거 문장"


# ─────────────────────────────────────────────────────────────
# 2026-09-17 추가 — build_user_citation_sources / collect_user_enrichment_evidence
# ─────────────────────────────────────────────────────────────


def test_build_user_citation_sources는_verified_functional과_data만_번호_매긴다():
    structured = {
        "requirements": {
            "functional": [
                {
                    "content": "가격을 비교해 보여준다.",
                    "evidence": {"quote": "가격을 비교해서 보여줍니다."},
                    "evidence_status": "verified",
                },
                {
                    "content": "미검증 기능.",
                    "evidence": {"quote": "원문에 없는 문장"},
                    "evidence_status": "unverified",
                },
            ],
            "data": [
                {
                    "content": "트렌드 지표를 저장한다.",
                    "evidence": {"quote": "트렌드 지표를 저장합니다."},
                    "evidence_status": "verified",
                }
            ],
        }
    }

    sources = build_user_citation_sources(structured)
    contents = [s["content"] for s in sources]

    assert "가격을 비교해 보여준다." in contents
    assert "트렌드 지표를 저장한다." in contents
    assert "미검증 기능." not in contents  # unverified는 보완 후보에서 제외


def test_collect_user_enrichment_evidence는_인용된_번호의_근거만_모은다():
    structured = {
        "requirements": {
            "functional": [
                {
                    "content": "가격을 비교해 보여준다.",
                    "evidence": {"quote": "가격을 비교해서 보여줍니다."},
                    "evidence_status": "verified",
                },
            ],
            "data": [],
        }
    }

    evidence = collect_user_enrichment_evidence([0], structured)
    assert [e.quote for e in evidence] == ["가격을 비교해서 보여줍니다."]
    assert evidence[0].status == "verified"


def test_collect_user_enrichment_evidence는_존재하지_않는_번호를_무시한다():
    structured = {"requirements": {"functional": [], "data": []}}
    assert collect_user_enrichment_evidence([0, 5], structured) == []

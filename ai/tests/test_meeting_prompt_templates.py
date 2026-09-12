"""
노드 1 회의록 구조화 프롬프트와 근거 검증 테스트.

실제 OpenAI API는 호출하지 않습니다.
"""

import json

import pytest

from meeting_analysis.prompt_loader import (
    build_extraction_fewshot_messages,
    build_extraction_system_prompt,
    load_extraction_fewshots,
    load_extraction_template,
)
from meeting_analysis.prompts import build_messages, build_system_prompt
from meeting_analysis.schemas import MeetingExtraction
from meeting_analysis.validators.evidence import verify_and_mark


def _evidence_test_data(problem_items: list[dict]) -> dict:
    """배경과 전체 문제까지 포함한 Evidence 검증용 데이터를 만듭니다."""
    return {
        "project": {
            "name": "재고 관리 서비스",
            "background": "재고를 수기로 관리하고 있다",
            "background_evidence": {
                "quote": "재고를 수기로 관리하고 있습니다.",
            },
            "problem": "발주 시점 누락으로 품절이 발생한다",
            "problem_evidence": {
                "quote": "발주 시점 누락으로 품절이 발생하고 있습니다.",
            },
            "problem_items": problem_items,
        }
    }


def _base_meeting_text(additional_text: str = "") -> str:
    """배경과 전체 문제 근거가 들어 있는 회의록을 만듭니다."""
    parts = [
        "재고를 수기로 관리하고 있습니다.",
        "발주 시점 누락으로 품절이 발생하고 있습니다.",
    ]
    if additional_text:
        parts.append(additional_text)
    return "\n".join(parts)


def test_extraction_template_has_expected_version():
    template = load_extraction_template()
    assert template["metadata"]["version"] == "2.1"


def test_extraction_template_contains_problem_items_rules():
    template = load_extraction_template()
    problem_items = template["project_rules"]["problem_items"]

    assert isinstance(problem_items, dict)
    assert problem_items["field"] == "project.problem_items"

    prompt = build_extraction_system_prompt()
    assert "project.problem_items" in prompt
    assert "구체적인 문제" in prompt
    assert "개별 문제" in prompt
    assert "evidence" in prompt


def test_extraction_template_keeps_project_goals_rules():
    template = load_extraction_template()
    goals = template["project_rules"]["goals"]

    assert isinstance(goals, dict)
    assert goals["field"] == "project.goals"

    prompt = build_extraction_system_prompt()
    assert "project.goals" in prompt
    assert "목표" in prompt
    assert "빈 배열" in prompt


def test_extraction_fewshots_match_meeting_schema():
    template = load_extraction_fewshots()

    assert template["metadata"]["version"] == "2.0"
    assert len(template["examples"]) == 2

    for example in template["examples"]:
        result = MeetingExtraction.model_validate(example["output"])
        assert result.project.name.strip()
        assert result.project.problem.strip()
        assert result.project.problem_items

        for problem_item in result.project.problem_items:
            assert problem_item.content.strip()
            assert problem_item.evidence.quote.strip()


def test_extraction_fewshot_message_roles():
    messages = build_extraction_fewshot_messages()

    assert len(messages) == 4
    assert [message["role"] for message in messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]

    for message in messages:
        if message["role"] == "assistant":
            MeetingExtraction.model_validate(json.loads(message["content"]))


def test_extraction_system_prompt_contains_required_fields():
    prompt = build_extraction_system_prompt()

    assert "project.problem" in prompt
    assert "project.problem_items" in prompt
    assert "project.goals" in prompt
    assert "요구사항 분류 규칙" in prompt
    assert "functional:" in prompt
    assert "non_functional:" in prompt
    assert "data:" in prompt
    assert "technical:" in prompt
    assert "evidence.quote" in prompt


def test_meeting_build_messages_adds_actual_input():
    meeting_text = "주문 상태 알림 기능을 추가하기로 했습니다."
    messages = build_messages(meeting_text)

    assert len(messages) == 5
    assert [message["role"] for message in messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]
    assert messages[-1] == {"role": "user", "content": meeting_text}


def test_meeting_build_messages_rejects_empty_input():
    with pytest.raises(ValueError, match="meeting_text가 비어 있습니다"):
        build_messages("   ")


def test_meeting_system_prompt_adds_glossary_when_provided():
    glossary = "안전재고: 품절 방지를 위해 유지하는 최소 재고"

    without_glossary = build_system_prompt()
    with_glossary = build_system_prompt(glossary)

    assert "안전재고:" not in without_glossary
    assert "안전재고:" in with_glossary
    assert "회의록 원문" in with_glossary
    assert "evidence.quote" in with_glossary


def test_problem_item_evidence_is_marked_verified():
    problem_quote = "수기 관리로 발주 시점을 놓쳐 품절이 발생하고 있습니다."
    meeting_text = _base_meeting_text(problem_quote)
    structured = _evidence_test_data(
        [
            {
                "content": "수기 관리로 발주 시점을 놓쳐 품절이 발생한다",
                "evidence": {"quote": problem_quote},
            }
        ]
    )

    report = verify_and_mark(structured, meeting_text)
    problem_item = structured["project"]["problem_items"][0]

    assert problem_item["evidence_status"] == "verified"
    assert report.checked == 3
    assert report.pass_rate == 1.0


def test_problem_item_evidence_is_marked_unverified():
    meeting_text = _base_meeting_text()
    structured = _evidence_test_data(
        [
            {
                "content": "월평균 10회의 품절이 발생한다",
                "evidence": {
                    "quote": "월평균 10회의 품절이 발생하고 있습니다.",
                },
            }
        ]
    )

    report = verify_and_mark(structured, meeting_text)
    problem_item = structured["project"]["problem_items"][0]

    assert problem_item["evidence_status"] == "unverified"
    assert report.checked == 3
    assert len(report.unverified) == 1
    assert report.pass_rate == pytest.approx(2 / 3)
    assert report.unverified[0].path == "project.problem_items[0]"


def test_problem_item_evidence_normalizes_whitespace():
    source_quote = "수기 관리로 발주 시점을 놓쳐\n품절이 발생하고 있습니다."
    submitted_quote = "수기 관리로 발주 시점을 놓쳐 품절이 발생하고 있습니다."
    meeting_text = _base_meeting_text(source_quote)
    structured = _evidence_test_data(
        [
            {
                "content": "발주 시점 누락으로 품절이 발생한다",
                "evidence": {"quote": submitted_quote},
            }
        ]
    )

    report = verify_and_mark(structured, meeting_text)
    problem_item = structured["project"]["problem_items"][0]

    assert problem_item["evidence_status"] == "verified"
    assert report.checked == 3
    assert report.pass_rate == 1.0


def test_problem_items_are_in_evidence_validation_paths():
    first_quote = "첫 번째 문제입니다."
    meeting_text = _base_meeting_text(first_quote)
    structured = _evidence_test_data(
        [
            {
                "content": "첫 번째 문제",
                "evidence": {"quote": first_quote},
            },
            {
                "content": "두 번째 문제",
                "evidence": {
                    "quote": "원문에 없는 두 번째 문제입니다.",
                },
            },
        ]
    )

    report = verify_and_mark(structured, meeting_text)
    problem_items = structured["project"]["problem_items"]

    assert problem_items[0]["evidence_status"] == "verified"
    assert problem_items[1]["evidence_status"] == "unverified"
    assert report.checked == 4
    assert len(report.unverified) == 1
    assert report.pass_rate == 0.75
    assert report.unverified[0].path == "project.problem_items[1]"

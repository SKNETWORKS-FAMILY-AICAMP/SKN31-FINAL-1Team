"""
노드 1 회의록 구조화 프롬프트와 근거 검증 테스트.

실제 OpenAI API는 호출하지 않습니다.

검증 대상:
    meeting_analysis/prompt_templates/extraction.yaml
    meeting_analysis/prompt_templates/extraction_fewshots.yaml
    meeting_analysis/prompt_loader.py
    meeting_analysis/prompts.py
    meeting_analysis/validators/evidence.py
"""

import json

import pytest

from meeting_analysis.prompt_loader import (
    build_extraction_fewshot_messages,
    build_extraction_system_prompt,
    load_extraction_fewshots,
    load_extraction_template,
)
from meeting_analysis.prompts import (
    build_messages,
    build_system_prompt,
)
from meeting_analysis.schemas import MeetingExtraction
from meeting_analysis.validators.evidence import (
    verify_and_mark,
)


def _evidence_test_data(
    problem_items: list[dict],
) -> dict:
    """
    Evidence 검증기가 기본적으로 검사하는
    project.background와 project.problem을 포함한 테스트 데이터를 만듭니다.

    개별 문제만 넣으면 배경과 전체 문제가 빈 값으로 검사되어
    전체 통과율 계산에 포함되므로 완전한 프로젝트 데이터를 사용합니다.
    """
    return {
        "project": {
            "name": "재고 관리 서비스",
            "background": "재고를 수기로 관리하고 있다",
            "background_evidence": {
                "quote": "재고를 수기로 관리하고 있습니다.",
            },
            "problem": "발주 시점 누락으로 품절이 발생한다",
            "problem_evidence": {
                "quote": (
                    "발주 시점 누락으로 "
                    "품절이 발생하고 있습니다."
                ),
            },
            "problem_items": problem_items,
        }
    }


def _base_meeting_text(
    additional_text: str = "",
) -> str:
    """배경과 전체 문제 근거가 포함된 회의록을 만듭니다."""
    parts = [
        "재고를 수기로 관리하고 있습니다.",
        "발주 시점 누락으로 품절이 발생하고 있습니다.",
    ]

    if additional_text:
        parts.append(additional_text)

    return "\n".join(parts)


def test_extraction_template_has_expected_version():
    """회의록 구조화 규칙 YAML의 버전을 확인합니다."""
    template = load_extraction_template()

    assert template["metadata"]["version"] == "2.3"


def test_extraction_template_contains_problem_items_rules():
    """개별 문제 필드와 작성 지침이 시스템 프롬프트에 있어야 합니다."""
    template = load_extraction_template()

    problem_items = template[
        "project_rules"
    ]["problem_items"]

    assert isinstance(problem_items, dict)

    assert (
        problem_items["field"]
        == "project.problem_items"
    )

    prompt = build_extraction_system_prompt()

    assert "project.problem_items" in prompt
    assert "구체적인 문제" in prompt
    assert "개별 문제" in prompt
    assert "evidence" in prompt


def test_extraction_template_keeps_project_goals_rules():
    """노드 1의 프로젝트 목표 추출 규칙도 유지해야 합니다."""
    template = load_extraction_template()

    goals = template[
        "project_rules"
    ]["goals"]

    assert isinstance(goals, dict)
    assert goals["field"] == "project.goals"

    prompt = build_extraction_system_prompt()

    assert "project.goals" in prompt
    assert "목표" in prompt
    assert "빈 배열" in prompt


def test_extraction_fewshots_match_meeting_schema():
    """모든 퓨샷 출력이 MeetingExtraction 스키마를 통과해야 합니다."""
    template = load_extraction_fewshots()

    assert template["metadata"]["version"] == "2.0"
    assert len(template["examples"]) == 2

    for example in template["examples"]:
        result = MeetingExtraction.model_validate(
            example["output"]
        )

        assert result.project.name.strip()
        assert result.project.problem.strip()
        assert result.project.problem_items

        for problem_item in result.project.problem_items:
            assert problem_item.content.strip()
            assert problem_item.evidence.quote.strip()

        for functional_item in result.requirements.functional:
            assert functional_item.feature_name


def test_extraction_fewshot_message_roles():
    """퓨샷 두 개는 user와 assistant 메시지 네 개가 되어야 합니다."""
    messages = build_extraction_fewshot_messages()

    assert len(messages) == 4

    assert [
        message["role"]
        for message in messages
    ] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]

    # assistant 메시지는 MeetingExtraction 형식의 JSON이어야 합니다.
    for message in messages:
        if message["role"] != "assistant":
            continue

        output = json.loads(
            message["content"]
        )

        MeetingExtraction.model_validate(output)


def test_extraction_system_prompt_contains_required_fields():
    """시스템 프롬프트에 프로젝트와 요구사항 규칙이 있어야 합니다."""
    prompt = build_extraction_system_prompt()

    assert "project.problem" in prompt
    assert "project.problem_items" in prompt
    assert "project.goals" in prompt

    # requirement_rules는 프롬프트에서 분류명으로 출력됩니다.
    assert "요구사항 분류 규칙" in prompt
    assert "functional:" in prompt
    assert "non_functional:" in prompt
    assert "data:" in prompt
    assert "technical:" in prompt

    for category in [
        "feature",
        "non_functional",
        "data",
        "tech",
        "scope",
    ]:
        assert f"decisions.category={category}" in prompt

    assert "evidence.quote" in prompt


def test_meeting_build_messages_adds_actual_input():
    """퓨샷 뒤에 실제 회의록이 user 메시지로 추가되어야 합니다."""
    meeting_text = (
        "주문 상태 알림 기능을 추가하기로 했습니다."
    )

    messages = build_messages(meeting_text)

    assert len(messages) == 5

    assert [
        message["role"]
        for message in messages
    ] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]

    assert messages[-1] == {
        "role": "user",
        "content": meeting_text,
    }


def test_meeting_build_messages_rejects_empty_input():
    """빈 회의록은 LLM 입력으로 만들지 않습니다."""
    with pytest.raises(
        ValueError,
        match="meeting_text가 비어 있습니다",
    ):
        build_messages("   ")


def test_meeting_system_prompt_adds_glossary_when_provided():
    """용어집은 전달된 경우에만 시스템 프롬프트에 포함됩니다."""
    glossary = (
        "안전재고: 품절 방지를 위해 유지하는 최소 재고"
    )

    without_glossary = build_system_prompt()
    with_glossary = build_system_prompt(glossary)

    assert "안전재고:" not in without_glossary
    assert "안전재고:" in with_glossary

    # 용어집 문장을 회의록 원문 근거로 사용하면 안 됩니다.
    assert "회의록 원문" in with_glossary
    assert "evidence.quote" in with_glossary


def test_problem_item_evidence_is_marked_verified():
    """개별 문제 quote가 원문에 있으면 verified로 표시합니다."""
    problem_quote = (
        "수기 관리로 발주 시점을 놓쳐 "
        "품절이 발생하고 있습니다."
    )

    meeting_text = _base_meeting_text(
        problem_quote
    )

    structured = _evidence_test_data(
        [
            {
                "content": (
                    "수기 관리로 발주 시점을 놓쳐 "
                    "품절이 발생한다"
                ),
                "evidence": {
                    "quote": problem_quote,
                },
            }
        ]
    )

    report = verify_and_mark(
        structured,
        meeting_text,
    )

    problem_item = structured[
        "project"
    ]["problem_items"][0]

    assert (
        problem_item["evidence_status"]
        == "verified"
    )

    # 배경, 전체 문제, 개별 문제 모두 검증됩니다.
    assert report.checked == 3
    assert report.pass_rate == 1.0


def test_problem_item_evidence_is_marked_unverified():
    """개별 문제 quote가 원문에 없으면 unverified로 표시합니다."""
    meeting_text = _base_meeting_text()

    structured = _evidence_test_data(
        [
            {
                "content": (
                    "월평균 10회의 품절이 발생한다"
                ),
                "evidence": {
                    "quote": (
                        "월평균 10회의 품절이 "
                        "발생하고 있습니다."
                    ),
                },
            }
        ]
    )

    report = verify_and_mark(
        structured,
        meeting_text,
    )

    problem_item = structured[
        "project"
    ]["problem_items"][0]

    assert (
        problem_item["evidence_status"]
        == "unverified"
    )

    # 배경과 전체 문제는 통과하고 개별 문제 하나만 실패합니다.
    assert report.checked == 3
    assert len(report.unverified) == 1
    assert report.pass_rate == pytest.approx(2 / 3)

    assert (
        report.unverified[0].path
        == "project.problem_items[0]"
    )


def test_problem_item_evidence_normalizes_whitespace():
    """줄바꿈과 연속 공백 차이는 같은 원문 근거로 처리합니다."""
    source_problem_quote = (
        "수기 관리로 발주 시점을 놓쳐\n"
        "품절이 발생하고 있습니다."
    )

    submitted_problem_quote = (
        "수기 관리로 발주 시점을 놓쳐 "
        "품절이 발생하고 있습니다."
    )

    meeting_text = _base_meeting_text(
        source_problem_quote
    )

    structured = _evidence_test_data(
        [
            {
                "content": (
                    "발주 시점 누락으로 품절이 발생한다"
                ),
                "evidence": {
                    "quote": submitted_problem_quote,
                },
            }
        ]
    )

    report = verify_and_mark(
        structured,
        meeting_text,
    )

    problem_item = structured[
        "project"
    ]["problem_items"][0]

    assert (
        problem_item["evidence_status"]
        == "verified"
    )

    assert report.checked == 3
    assert report.pass_rate == 1.0


def test_problem_items_are_in_evidence_validation_paths():
    """개별 문제 각각이 Evidence 검증 대상에 포함되어야 합니다."""
    first_quote = "첫 번째 문제입니다."

    meeting_text = _base_meeting_text(
        first_quote
    )

    structured = _evidence_test_data(
        [
            {
                "content": "첫 번째 문제",
                "evidence": {
                    "quote": first_quote,
                },
            },
            {
                "content": "두 번째 문제",
                "evidence": {
                    "quote": (
                        "원문에 없는 두 번째 문제입니다."
                    ),
                },
            },
        ]
    )

    report = verify_and_mark(
        structured,
        meeting_text,
    )

    problem_items = structured[
        "project"
    ]["problem_items"]

    assert (
        problem_items[0]["evidence_status"]
        == "verified"
    )

    assert (
        problem_items[1]["evidence_status"]
        == "unverified"
    )

    # 배경, 전체 문제, 개별 문제 2개를 합쳐 총 4개입니다.
    assert report.checked == 4
    assert len(report.unverified) == 1
    assert report.pass_rate == 0.75

    assert (
        report.unverified[0].path
        == "project.problem_items[1]"
    )

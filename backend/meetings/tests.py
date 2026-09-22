from django.contrib.auth import get_user_model
from django.test import TestCase
from types import SimpleNamespace
from unittest.mock import patch

from meetings import services as meetings_services
from meetings.models import MeetingNote, SpecDocument
from meetings.services import (
    _build_evidence_items,
    _normalize_plan_html,
    run_meeting_analysis,
)


class PlanHtmlNormalizationTests(TestCase):
    def test_parenthesized_numbers_in_html_are_split_into_paragraphs(self):
        value = '<p><strong>목표:</strong> 3단계 필터링. (1) 키워드 매칭 (2) 관련성 평가 (3) 감성 분석</p>'
        normalized = _normalize_plan_html(value)
        self.assertEqual(
            normalized,
            '<p><strong>목표:</strong> 3단계 필터링.</p><p>(1) 키워드 매칭</p><p>(2) 관련성 평가</p><p>(3) 감성 분석</p>',
        )

    def test_parenthesized_numbers_in_plain_text_keep_numbers(self):
        normalized = _normalize_plan_html('(1) 첫 번째 (2) 두 번째 (3) 세 번째')
        self.assertEqual(normalized, '<p>(1) 첫 번째</p><p>(2) 두 번째</p><p>(3) 세 번째</p>')


class EvidenceItemsTests(TestCase):
    """
    2026-09-18: 회의록 전체원문 근거연동 UI("원문 보기" 패널) 준비용
    _build_evidence_items가 항목 단위 근거를 올바른 필드명으로 묶는지 확인한다.
    """

    def test_features_섹션은_기능별로_인용문을_따로_묶는다(self):
        plan_dict = {
            "sections": [
                {
                    "key": "overview",
                    "evidence": [
                        {"quote": "서비스 개요 근거", "status": "verified"},
                        {"quote": "검증 안 된 근거", "status": "unverified"},
                    ],
                },
                {
                    "key": "features",
                    "evidence": [],
                    "features": [
                        {"title": "기능 A", "source_indices": [0, 1]},
                        {"title": "기능 B", "source_indices": [1]},
                        {"title": "기능 C", "source_indices": []},
                    ],
                },
            ],
        }
        structured = {
            "requirements": {
                "functional": [
                    {"content": "요구 0", "evidence": {"quote": "원문 인용 0"}, "evidence_status": "verified"},
                    {"content": "요구 1", "evidence": {"quote": "원문 인용 1"}, "evidence_status": "verified"},
                ],
            },
            "decisions": [],
        }

        result = _build_evidence_items(plan_dict, structured)

        self.assertEqual(result["overview"], {"quotes": ["서비스 개요 근거"]})
        self.assertEqual(
            result["key_features"]["items"],
            [
                {"title": "기능 A", "quotes": ["원문 인용 0", "원문 인용 1"]},
                {"title": "기능 B", "quotes": ["원문 인용 1"]},
                {"title": "기능 C", "quotes": []},
            ],
        )

    def test_근거가_전혀_없는_섹션은_결과에서_빠진다(self):
        plan_dict = {"sections": [{"key": "problem", "evidence": []}]}
        result = _build_evidence_items(plan_dict, {})
        self.assertEqual(result, {})

    def test_원문_직접_생성_기능과_구조화_결정을_보존한다(self):
        plan_dict = {
            "sections": [
                {
                    "key": "features",
                    "evidence": [{"quote": "기능 근거", "status": "verified"}],
                    "features": [
                        {
                            "title": "직접 생성 기능",
                            "source_indices": [],
                            "evidence": [{"quote": "기능 근거"}],
                        }
                    ],
                },
                {
                    "key": "decisions",
                    "evidence": [{"quote": "결정 근거", "status": "verified"}],
                    "items": ["[기술] 저장소를 분리한다. (이유: 관리 부담을 줄인다.)"],
                },
            ]
        }

        result = _build_evidence_items(plan_dict, {})

        self.assertEqual(
            result["key_features"]["items"],
            [{"title": "직접 생성 기능", "quotes": ["기능 근거"]}],
        )
        self.assertEqual(
            result["final_decisions"]["structured_items"],
            ["[기술] 저장소를 분리한다. (이유: 관리 부담을 줄인다.)"],
        )


class MeetingPlanPipelineTests(TestCase):
    def test_web_generation_passes_source_text_without_calling_analyze_meeting(self):
        """2026-09-21(PLAN_GENERATION_HANDOFF): 웹 경로는 더 이상 무거운
        meeting_analysis 전체 구조화 노드를 호출하지 않는다. 회의록 원문만
        담은 입력을 기획서 노드(plan_draft.agent.run())에 바로 전달하고,
        기본 전략(parallel)이 원문을 직접 읽어 1~7번을 채운다."""
        user = get_user_model().objects.create_user(username="pipeline-user")
        note = MeetingNote.objects.create(
            title="파이프라인 테스트", content="원문 회의 내용", created_by=user,
        )
        sections = [
            {
                "key": key, "content_html": f"<p>{key} 내용</p>",
                "items": [], "features": [], "evidence": [],
            }
            for key in ("overview", "problem", "goals", "users", "features", "tech_scope", "decisions")
        ]
        captured = {}

        def fake_generate(data, proposal_id, on_stage=None):
            captured.update(data)
            return SimpleNamespace(model_dump=lambda **_kwargs: {"sections": sections})

        with patch("meetings.services.generate_plan", side_effect=fake_generate) as generate:
            result = run_meeting_analysis(note.pk, user.pk)

        self.assertEqual(result["status"], "success")
        generate.assert_called_once()
        self.assertFalse(hasattr(meetings_services, "analyze_meeting"))
        self.assertEqual(captured["project"], {})
        self.assertEqual(captured["plan_source_text"], "원문 회의 내용")
        self.assertEqual(captured["meeting_id"], str(note.pk))
        spec = SpecDocument.objects.get(meeting=note)
        self.assertNotEqual(spec.overview, "회의에서 논의되지 않았습니다.")

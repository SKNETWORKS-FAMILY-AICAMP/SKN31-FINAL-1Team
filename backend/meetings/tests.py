from django.contrib.auth import get_user_model
from django.test import TestCase

from meetings.models import MeetingNote, SpecDocument, SpecValidationReport
from meetings.serializers import MeetingNoteSerializer
from meetings.services import (
    PLAN_FIELDS,
    _build_evidence_items,
    _normalize_plan_html,
    apply_spec_validation,
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


class SpecValidationApplyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='plan-review-user')
        self.note = MeetingNote.objects.create(
            title='검증 테스트 회의', content='기존 내용에 신규 기능을 추가한다.',
            created_by=self.user,
        )
        self.source = SpecDocument.objects.create(
            meeting=self.note,
            title='검증 테스트 기획 초안',
            **{field: f'<p>기존 {field}</p>' for field in PLAN_FIELDS},
        )

    def test_apply_creates_revised_version_and_serializer_returns_it_first(self):
        revised_document = {
            field: (f'<p>보완된 {field}</p>' if field == 'key_features' else getattr(self.source, field))
            for field in PLAN_FIELDS
        }
        report = SpecValidationReport.objects.create(
            spec=self.source,
            revised_document=revised_document,
            created_by=self.user,
        )

        revised = apply_spec_validation(report)

        self.assertEqual(revised.version, 2)
        self.assertEqual(revised.parent_spec, self.source)
        self.assertEqual(revised.key_features, '<p>보완된 key_features</p>')
        self.source.refresh_from_db()
        self.assertEqual(self.source.key_features, '<p>기존 key_features</p>')
        serialized = MeetingNoteSerializer(self.note).data['spec_documents']
        self.assertEqual([item['version'] for item in serialized], [2, 1])
        self.assertEqual(serialized[0]['key_features'], '<p>보완된 key_features</p>')

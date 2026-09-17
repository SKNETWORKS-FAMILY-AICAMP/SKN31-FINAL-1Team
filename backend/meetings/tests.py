from django.contrib.auth import get_user_model
from django.test import TestCase

from meetings.models import MeetingNote, SpecDocument, SpecValidationReport
from meetings.serializers import MeetingNoteSerializer
from meetings.services import PLAN_FIELDS, apply_spec_validation


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

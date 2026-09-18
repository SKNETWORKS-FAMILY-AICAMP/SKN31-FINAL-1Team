from django.contrib.auth import get_user_model
from django.test import TestCase

from meetings.models import MeetingNote, SpecDocument
from requirements.models import RequirementDefinition, RequirementItem, RequirementValidationReport
from requirements.services import apply_requirement_validation


class RequirementValidationApplyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='requirement-review-user')
        self.note = MeetingNote.objects.create(
            title='요구사항 검증 회의', content='사용자는 이메일로 로그인한다.', created_by=self.user,
        )
        self.spec = SpecDocument.objects.create(
            meeting=self.note, title='로그인 기획서', key_features='<p>이메일 로그인</p>',
        )
        self.source = RequirementDefinition.objects.create(
            spec=self.spec, title='로그인 요구사항정의서', version='v1.0', created_by=self.user,
        )
        RequirementItem.objects.create(
            req_def=self.source, req_code='FR-01-001', req_name='로그인',
            description='로그인한다.', order=1,
        )

    def test_apply_preserves_source_and_creates_revised_version(self):
        report = RequirementValidationReport.objects.create(
            requirement_definition=self.source, created_by=self.user,
            revised_items=[{
                'req_code': 'FR-01-001', 'req_name': '이메일 로그인',
                'description': '이메일과 비밀번호로 로그인한다.',
                'related_feature': '이메일 로그인', 'input_output': '이메일 입력, 인증 결과 출력',
                'acceptance_criteria': '올바른 계정이면 인증 토큰을 반환한다.',
                'note': '기획서 근거', 'source': 'requirement_text', 'review_status': '검토완료',
                'priority': 'MEDIUM', 'difficulty': '중', 'category': '기능', 'category_2': '인증',
            }],
        )

        revised = apply_requirement_validation(report)

        self.assertEqual(revised.version, 'v2.0')
        self.assertEqual(revised.parent_definition, self.source)
        self.assertEqual(revised.items.get().req_name, '이메일 로그인')
        self.assertEqual(self.source.items.get().req_name, '로그인')
        report.refresh_from_db()
        self.assertEqual(report.applied_definition, revised)

    def test_apply_is_idempotent(self):
        report = RequirementValidationReport.objects.create(
            requirement_definition=self.source, created_by=self.user,
            revised_items=[{
                'req_code': 'FR-01-001', 'req_name': '보완 로그인', 'description': '보완 내용',
            }],
        )
        first = apply_requirement_validation(report)
        second = apply_requirement_validation(report)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(RequirementDefinition.objects.filter(spec=self.spec).count(), 2)

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from dashboard.system_logs import MAX_LINES, redact, tail_log


class SystemLogReadTests(SimpleTestCase):
    def test_tail_is_bounded_and_redacts_credentials(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'django.log'
            path.write_text('line\n' * 300 + 'authorization: Bearer abc123\nOPENAI_API_KEY=sk-example-secret-123456\n', encoding='utf-8')
            lines, truncated = tail_log(path)
        self.assertTrue(truncated)
        self.assertLessEqual(len(lines), MAX_LINES)
        self.assertNotIn('abc123', '\n'.join(lines))
        self.assertNotIn('sk-example-secret-123456', '\n'.join(lines))

    def test_missing_log_is_empty(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(tail_log(Path(tmp) / 'missing.log'), ([], False))


class SystemLogPermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.pm = get_user_model().objects.create_user(username='log-pm', is_staff=True)
        self.member = get_user_model().objects.create_user(username='log-member')

    def test_only_pm_can_read_log(self):
        self.assertEqual(self.client.get('/api/dashboard/system-logs/').status_code, 401)
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get('/api/dashboard/system-logs/').status_code, 403)
        self.client.force_authenticate(self.pm)
        with patch('dashboard.system_logs.tail_log', return_value=(['[2026-10-06] ERROR example'], False)):
            response = self.client.get('/api/dashboard/system-logs/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['lines'], ['[2026-10-06] ERROR example'])

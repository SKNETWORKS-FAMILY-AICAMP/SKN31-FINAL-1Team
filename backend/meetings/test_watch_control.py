from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from meetings.models import MeetingWatchSetting
from meetings.watch_control import validate_folder, normalize_folder
from projects.models import Project


class WatchControlTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username='watch-owner')
        self.other = get_user_model().objects.create_user(username='watch-other')
        self.project = Project.objects.create(name='Watch', owner=self.owner)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_each_employee_has_an_independent_switch(self):
        with TemporaryDirectory() as tmp, patch('meetings.watch_control.allowed_root', return_value=Path(tmp)), \
             patch('meetings.watch_views.ensure_process') as start:
            start.side_effect = lambda control_id: MeetingWatchSetting.objects.get(pk=control_id)
            response = self.client.post('/api/meetings/watch-control/',
                                        {'enabled': True, 'project_id': self.project.pk, 'folder': tmp}, format='json')
            self.assertEqual(response.status_code, 200, response.data)
            self.assertTrue(MeetingWatchSetting.objects.get(user=self.owner).enabled)
            self.client.force_authenticate(self.other)
            self.assertFalse(self.client.get('/api/meetings/watch-control/').data['enabled'])
            self.assertFalse(MeetingWatchSetting.objects.get(user=self.other).enabled)
            self.client.force_authenticate(self.owner)
            self.assertEqual(self.client.post('/api/meetings/watch-control/', {'enabled': False}, format='json').status_code, 200)
            self.assertFalse(MeetingWatchSetting.objects.get(user=self.owner).enabled)

    def test_employee_can_save_folder_while_off(self):
        with TemporaryDirectory() as tmp, patch('meetings.watch_control.allowed_root', return_value=Path(tmp)):
            response = self.client.patch('/api/meetings/watch-control/', {'folder': tmp}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MeetingWatchSetting.objects.get(user=self.owner).folder, tmp)

    def test_other_user_cannot_use_project_they_do_not_own(self):
        self.client.force_authenticate(self.other)
        with TemporaryDirectory() as tmp, patch('meetings.watch_control.allowed_root', return_value=Path(tmp)):
            response = self.client.post('/api/meetings/watch-control/',
                                        {'enabled': True, 'project_id': self.project.pk, 'folder': tmp}, format='json')
            self.assertEqual(response.status_code, 403)

    def test_windows_path_is_normalized(self):
        self.assertEqual(str(normalize_folder(r'C:\\Users\\Playdata\\Desktop\\회의록')),
                         '/mnt/c/Users/Playdata/Desktop/회의록')

    def test_folder_must_be_within_allowed_root(self):
        with TemporaryDirectory() as allowed, TemporaryDirectory() as outside, \
             patch('meetings.watch_control.allowed_root', return_value=Path(allowed)):
            with self.assertRaises(ValueError):
                validate_folder(outside)
            self.assertEqual(validate_folder(allowed), Path(allowed).resolve())

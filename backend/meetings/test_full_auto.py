from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.core.management import call_command
from io import StringIO
from rest_framework.test import APIClient
from common.models import CommonCode, CommonCodeGroup
from meetings.models import MeetingNote, SpecDocument, FullAutoJob
from meetings.full_auto import run_full_auto_job
from projects.models import Project, PipelineHistory
from requirements.models import RequirementDefinition, RequirementItem
from tasks.models import TaskAssignment


class FullAutoTests(TestCase):
    def setUp(self):
        self.pm = get_user_model().objects.create_user(username='auto-pm', is_staff=True)
        self.member = get_user_model().objects.create_user(username='auto-member')
        self.project = Project.objects.create(name='Automation', owner=self.pm)
        self.client = APIClient()
        self.client.force_authenticate(self.pm)
        for group, code in [('PROPOSAL_STATUS', 'PROPOSAL_APPROVED'), ('REQSPEC_STATUS', 'APPROVED'), ('TASK_STATUS', 'PENDING_APPROVAL')]:
            g, _ = CommonCodeGroup.objects.get_or_create(group_code=group, defaults={'group_name': group})
            CommonCode.objects.get_or_create(code_id=code, defaults={'group': g, 'code_name': code})

    def create_note(self, **extra):
        return self.client.post('/api/meetings/notes/', dict(project=self.project.pk, title='Meeting', content='Build a task board', **extra), format='json')

    def setup_job(self):
        response = self.create_note()
        self.assertEqual(response.status_code, 201, response.data)
        self.job = FullAutoJob.objects.get(note_id=response.data['id'])
        self.spec = SpecDocument.objects.create(meeting=self.job.note, title='Plan')
        self.req = RequirementDefinition.objects.create(spec=self.spec, project=self.project, title='Requirements')
        RequirementItem.objects.create(req_def=self.req, req_code='FR-01', req_name='Board', description='Board')
        self.suggestion = dict(unit_id='T1', source_req_id='FR-01', assignee_id=self.member.pk,
                               title='Board', description='Build board', estimated_hours=4)
        return self.job

    def mocked_run(self, **output):
        generated = dict(status='success', req_def_id=self.req.pk, suggestions=[self.suggestion])
        generated.update(output)
        with patch('meetings.full_auto.run_meeting_analysis', return_value={'status': 'success', 'created_spec': {'id': self.spec.pk}}) as analyze, \
             patch('requirements.views.process_ai_requirement_extraction', return_value=self.req) as extract, \
             patch('tasks.services.generate_task_suggestions', return_value=generated) as generate:
            claimed = run_full_auto_job(self.job.pk)
        self.job.refresh_from_db()
        return claimed, analyze, extract, generate

    def test_pm_registration_queues_without_calling_ai(self):
        with patch('meetings.full_auto.run_meeting_analysis') as analyze:
            response = self.create_note()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['full_auto']['status'], 'PENDING')
        self.assertEqual(FullAutoJob.objects.count(), 1)
        analyze.assert_not_called()

    def test_opt_out_preserves_manual_workflow(self):
        self.assertEqual(self.create_note(auto_run=False).status_code, 201)
        self.assertFalse(FullAutoJob.objects.exists())

    def test_member_registration_queues_automatic_workflow(self):
        self.client.force_authenticate(self.member)
        response = self.create_note()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(FullAutoJob.objects.get().created_by_id, self.member.pk)

    def test_complete_pipeline_persists_assignments_once(self):
        self.setup_job()
        self.mocked_run()
        self.assertEqual(self.job.status, 'SUCCESS', self.job.error_message)
        self.spec.refresh_from_db()
        self.req.refresh_from_db()
        self.assertEqual(self.spec.status_code_id, 'PROPOSAL_APPROVED')
        self.assertIsNone(self.spec.reviewer_id)
        self.assertEqual(self.req.status_code_id, 'APPROVED')
        task = TaskAssignment.objects.get(req_item__req_def=self.req)
        self.assertEqual(task.assigned_user_id, self.member.pk)
        self.assertEqual(task.status_code_id, 'PENDING_APPROVAL')
        self.assertFalse(run_full_auto_job(self.job.pk))
        self.assertEqual(TaskAssignment.objects.count(), 1)
        self.assertTrue(PipelineHistory.objects.filter(step_type='TASK_ASSIGNED').exists())

    def test_failure_stops_and_retry_reuses_completed_documents(self):
        self.setup_job()
        self.mocked_run(status='error', message='AI unavailable')
        self.assertEqual(self.job.status, 'ERROR')
        self.assertFalse(TaskAssignment.objects.exists())
        response = self.client.post(f'/api/meetings/notes/{self.job.note_id}/full-auto/')
        self.assertEqual(response.status_code, 202)
        _, analyze, extract, generate = self.mocked_run()
        analyze.assert_not_called()
        extract.assert_not_called()
        generate.assert_called_once()
        self.assertEqual(self.job.status, 'SUCCESS', self.job.error_message)

    def test_unassigned_tasks_do_not_auto_confirm(self):
        self.setup_job()
        self.mocked_run(suggestions=[dict(self.suggestion, assignee_id=None)])
        self.assertEqual(self.job.status, 'ERROR')
        self.assertIn('미배정', self.job.error_message)
        self.assertFalse(TaskAssignment.objects.exists())

    def test_manual_generation_blocked_while_queued(self):
        self.setup_job()
        self.assertEqual(self.client.post(f'/api/meetings/notes/{self.job.note_id}/analyze/').status_code, 409)
        self.assertEqual(self.client.post(f'/api/requirements/{self.spec.pk}/generate-tasks/').status_code, 409)
        self.assertEqual(self.client.patch(f'/api/meetings/notes/{self.job.note_id}/', {'content': 'Changed'}).status_code, 409)

    def test_status_access_and_retry_conflict(self):
        self.setup_job()
        url = f'/api/meetings/notes/{self.job.note_id}/full-auto/'
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url).status_code, 409)
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url).status_code, 403)

    def test_inactive_requester_does_not_execute(self):
        self.setup_job()
        self.pm.is_active = False
        self.pm.save()
        _, analyze, extract, generate = self.mocked_run()
        self.assertEqual(self.job.status, 'ERROR')
        analyze.assert_not_called()
        extract.assert_not_called()
        generate.assert_not_called()

    def test_confirmation_and_completion_rollback_together(self):
        self.setup_job()
        create_history = PipelineHistory.objects.create

        def fail_after_assignment(**kwargs):
            if kwargs['step_type'] == 'TASK_ASSIGNED':
                raise RuntimeError('History storage failed')
            return create_history(**kwargs)

        with patch('meetings.full_auto.PipelineHistory.objects.create', side_effect=fail_after_assignment):
            self.mocked_run()
        self.assertEqual(self.job.status, 'ERROR')
        self.assertFalse(PipelineHistory.objects.filter(step_type='TASK_ASSIGNED').exists())
        self.assertFalse(TaskAssignment.objects.exists())

    def test_worker_recovers_interrupted_job_and_processes_once(self):
        self.setup_job()
        self.job.status = 'RUNNING'
        self.job.save()
        with patch('meetings.management.commands.run_full_auto_worker.run_full_auto_job') as run:
            call_command('run_full_auto_worker', once=True, recover_job=str(self.job.pk), stdout=StringIO())
        run.assert_called_once_with(self.job.pk)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'PENDING')


    def test_owner_can_start_previously_registered_meeting(self):
        self.client.force_authenticate(self.member)
        response = self.create_note(auto_run=False)
        note_id = response.data['id']
        self.assertEqual(self.client.post(f'/api/meetings/notes/{note_id}/full-auto/').status_code, 202)
        self.assertEqual(FullAutoJob.objects.get().note_id, note_id)
        self.assertEqual(self.client.post(f'/api/meetings/notes/{note_id}/full-auto/').status_code, 409)


    def test_existing_plan_is_reused_for_member_auto_run(self):
        self.client.force_authenticate(self.member)
        response = self.create_note(auto_run=False)
        note = MeetingNote.objects.get(pk=response.data['id'])
        spec = SpecDocument.objects.create(meeting=note, title='Existing plan')
        response = self.client.post(f'/api/meetings/notes/{note.pk}/full-auto/')
        self.assertEqual(response.status_code, 202)
        job = FullAutoJob.objects.get(note=note)
        self.assertEqual(job.spec_id, spec.pk)
        with patch('meetings.full_auto.run_meeting_analysis') as analyze, patch('requirements.views.process_ai_requirement_extraction', side_effect=RuntimeError('stop after approval')):
            run_full_auto_job(job.pk)
        analyze.assert_not_called()
        spec.refresh_from_db()
        self.assertEqual(spec.status_code_id, 'PROPOSAL_APPROVED')

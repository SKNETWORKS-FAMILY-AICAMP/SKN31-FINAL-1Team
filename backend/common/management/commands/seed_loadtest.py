"""Create a fixed, synthetic baseline in the local load-test database only."""
from datetime import timedelta
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from common.models import CommonCode
from meetings.models import MeetingNote, SpecDocument
from notifications.models import Notification
from projects.models import Project, PipelineHistory
from requirements.models import RequirementDefinition, RequirementItem
from tasks.models import TaskAssignment, TaskStatusCode


class Command(BaseCommand):
    help = 'Seed 20 users, 10 projects and 200 tasks; refuses non-local databases.'

    def handle(self, *args, **options):
        cfg = connection.settings_dict
        if not (cfg['HOST'] == '127.0.0.1' and str(cfg['PORT']) == '3307'
                and cfg['NAME'] == 'heyzzabi_test'):
            raise CommandError('Only 127.0.0.1:3307/heyzzabi_test is allowed.')
        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            raise CommandError('Apply pending migrations before seeding.')
        User = get_user_model()
        # A repeated invocation never changes passwords or resets edited fixtures.
        if User.objects.filter(username__startswith='lt_small_').exists():
            raise CommandError('lt_small_ dataset already exists; no data changed.')
        codes = CommonCode.objects.in_bulk()
        required = ['ACTIVE', 'DRAFT', 'PENDING_APPROVAL', 'TASK_APPROVED', 'IN_PROGRESS', 'DONE']
        if any(key not in codes for key in required):
            raise CommandError('Required common codes are missing.')
        today = timezone.localdate()
        password = os.environ.get('LOADTEST_PASSWORD', 'LocalLoad2026!')
        with transaction.atomic():
            users = []
            for i in range(20):
                u = User.objects.create_user(
                    username=f'lt_small_{i+1:03}', password=password,
                    first_name=f'테스트{i+1:03}', last_name='합성',
                    email=f'lt_small_{i+1:03}@example.invalid',
                    is_staff=i < 4, is_active=True, is_onboarded=True,
                    status_code=codes['ACTIVE'], hire_date=today-timedelta(days=365),
                )
                users.append(u)
                Notification.objects.create(user=u, message='[LOADTEST small] 합성 테스트 알림')
            statuses = [TaskStatusCode.PENDING_APPROVAL, TaskStatusCode.APPROVED,
                        TaskStatusCode.IN_PROGRESS, TaskStatusCode.COMPLETED]
            for i in range(10):
                owner = users[i % 4]
                project = Project.objects.create(
                    name=f'[LOADTEST small] 프로젝트 {i+1:02}', owner=owner,
                    description='로컬 조회·수정 성능 점검용 합성 데이터. AI 생성 결과 아님.',
                    period_start=today, period_end=today+timedelta(days=60))
                note = MeetingNote.objects.create(
                    project=project, created_by=owner, title=f'[LOADTEST small] 회의 {i+1:02}',
                    content='테스트 협업 서비스의 로그인, 업무 조회, 진행률 수정 기능을 구현한다. '
                            'PM이 업무를 검토하고 일반 사용자는 본인 업무를 처리한다.\n'*30,
                    meeting_date=timezone.now(), status=MeetingNote.Status.REVIEWED)
                spec = SpecDocument.objects.create(
                    meeting=note, title=f'[LOADTEST small] 기획서 {i+1:02}',
                    overview='합성 협업 서비스', problem_definition='업무 누락 방지',
                    goals='조회와 수정 기능 구현', target_users='PM 및 팀원',
                    key_features='로그인, 업무 목록, 진행률 수정', tech_stack='Django, MySQL',
                    final_decisions='PM 검토 후 확정', period_start=today,
                    period_end=today+timedelta(days=60))
                definition = RequirementDefinition.objects.create(
                    spec=spec, project=project, created_by=owner,
                    title=f'[LOADTEST small] 요구사항 {i+1:02}', status_code=codes['DRAFT'])
                for j in range(20):
                    item = RequirementItem.objects.create(
                        req_def=definition, req_code=f'LT-{i+1:02}-{j+1:03}',
                        req_name=f'합성 기능 {j+1:03}', description='담당자는 업무 정보를 조회할 수 있다.',
                        acceptance_criteria='본인 업무가 목록에 표시되는지 확인한다.',
                        category='FR', category_2='업무 관리', order=j+1)
                    assignee = users[4+(i*20+j)%16]
                    TaskAssignment.objects.create(
                        req_item=item, project=project, assigned_user=assignee,
                        task_no=f'LT-S-{i+1:02}-{j+1:03}', title=f'합성 업무 {j+1:03}',
                        description='부하테스트용 합성 업무', estimated_hours=4,
                        status_code=codes[statuses[j%4]], progress=[0,0,50,100][j%4],
                        start_date=today+timedelta(days=j), end_date=today+timedelta(days=j+2))
                PipelineHistory.objects.create(
                    project=project, meeting=note, spec=spec, requirement=definition,
                    actor=owner, step_type='MEETING_REGISTERED', title='[LOADTEST small] 합성 데이터 준비')
        self.stdout.write(self.style.SUCCESS(
            'Created: users=20 (PM=4), projects=10, meetings=10, specs=10, '
            'definitions=10, items=200, tasks=200, notifications=20, histories=10.'))

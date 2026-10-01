"""Extend the local synthetic dataset from 10/200 to 50 projects/2,000 tasks."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from common.models import CommonCode
from meetings.models import MeetingNote, SpecDocument
from notifications.models import Notification
from projects.models import PipelineHistory, Project
from requirements.models import RequirementDefinition, RequirementItem
from tasks.models import TaskAssignment, TaskStatusCode


class Command(BaseCommand):
    help = "Add 40 projects and 1,800 tasks to the local load-test database."

    def handle(self, *args, **options):
        cfg = connection.settings_dict
        if not (
            cfg["HOST"] == "127.0.0.1"
            and str(cfg["PORT"]) == "3307"
            and cfg["NAME"] == "heyzzabi_test"
        ):
            raise CommandError("Only 127.0.0.1:3307/heyzzabi_test is allowed.")
        if Project.objects.filter(name__startswith="[LOADTEST scale]").exists():
            raise CommandError("[LOADTEST scale] dataset already exists; no data changed.")

        User = get_user_model()
        users = list(User.objects.filter(username__startswith="lt_small_").order_by("username"))
        if len(users) != 20:
            raise CommandError("Expected exactly 20 lt_small_ users.")
        codes = CommonCode.objects.in_bulk()
        statuses = [
            TaskStatusCode.PENDING_APPROVAL,
            TaskStatusCode.APPROVED,
            TaskStatusCode.IN_PROGRESS,
            TaskStatusCode.COMPLETED,
        ]
        required = ["DRAFT", *statuses]
        if any(code not in codes for code in required):
            raise CommandError("Required common codes are missing.")

        today = timezone.localdate()
        with transaction.atomic():
            for project_index in range(40):
                number = project_index + 11
                owner = users[project_index % 4]
                project = Project.objects.create(
                    name=f"[LOADTEST scale] 프로젝트 {number:02}",
                    owner=owner,
                    description="로컬 데이터 증가 성능 점검용 합성 프로젝트.",
                    period_start=today,
                    period_end=today + timedelta(days=90),
                )
                note = MeetingNote.objects.create(
                    project=project,
                    created_by=owner,
                    title=f"[LOADTEST scale] 회의 {number:02}",
                    content=("대규모 업무 목록과 대시보드 조회 성능을 점검한다.\n" * 30),
                    meeting_date=timezone.now(),
                    status=MeetingNote.Status.REVIEWED,
                )
                spec = SpecDocument.objects.create(
                    meeting=note,
                    title=f"[LOADTEST scale] 기획서 {number:02}",
                    overview="합성 데이터 규모 확대",
                    problem_definition="대량 조회 지연 확인",
                    goals="목록과 집계 성능 확인",
                    target_users="PM 및 팀원",
                    key_features="업무 조회, 프로젝트 조회, 대시보드",
                    tech_stack="Django, MySQL",
                    final_decisions="로컬 합성 데이터만 사용",
                    period_start=today,
                    period_end=today + timedelta(days=90),
                )
                definition = RequirementDefinition.objects.create(
                    spec=spec,
                    project=project,
                    created_by=owner,
                    title=f"[LOADTEST scale] 요구사항 {number:02}",
                    status_code=codes["DRAFT"],
                )
                items = []
                for task_index in range(45):
                    items.append(
                        RequirementItem(
                            req_def=definition,
                            req_code=f"LTS-{number:02}-{task_index + 1:03}",
                            req_name=f"확대 합성 기능 {task_index + 1:03}",
                            description="담당자는 대규모 업무 목록을 조회할 수 있다.",
                            acceptance_criteria="목록 응답에 해당 업무가 포함되는지 확인한다.",
                            category="FR",
                            category_2="업무 관리",
                            order=task_index + 1,
                        )
                    )
                RequirementItem.objects.bulk_create(items, batch_size=200)
                created_items = list(definition.items.order_by("order", "id"))
                tasks = []
                for task_index, item in enumerate(created_items):
                    assignee = users[4 + (project_index * 45 + task_index) % 16]
                    status = statuses[task_index % len(statuses)]
                    tasks.append(
                        TaskAssignment(
                            req_item=item,
                            project=project,
                            assigned_user=assignee,
                            task_no=f"LT-L-{number:02}-{task_index + 1:03}",
                            title=f"확대 합성 업무 {task_index + 1:03}",
                            description="대량 목록 부하테스트용 합성 업무",
                            estimated_hours=4,
                            status_code=codes[status],
                            progress=[0, 0, 50, 100][task_index % 4],
                            start_date=today + timedelta(days=task_index % 30),
                            end_date=today + timedelta(days=task_index % 30 + 2),
                        )
                    )
                TaskAssignment.objects.bulk_create(tasks, batch_size=200)
                PipelineHistory.objects.create(
                    project=project,
                    meeting=note,
                    spec=spec,
                    requirement=definition,
                    actor=owner,
                    step_type="MEETING_REGISTERED",
                    title="[LOADTEST scale] 합성 데이터 확대",
                )
                Notification.objects.create(
                    user=owner,
                    message=f"[LOADTEST scale] 프로젝트 {number:02} 준비 완료",
                )

        counts = {
            "projects": Project.objects.count(),
            "tasks": TaskAssignment.objects.count(),
            "requirements": RequirementItem.objects.count(),
        }
        if counts["projects"] != 50 or counts["tasks"] != 2000 or counts["requirements"] != 2000:
            raise CommandError(f"Unexpected final counts: {counts}")
        self.stdout.write(self.style.SUCCESS(f"Scale dataset created: {counts}"))

from datetime import timedelta
from django.db.models import Count, Avg, F, ExpressionWrapper, fields, Q
from django.utils import timezone
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

# users/permissions.py에서 생성한 IsPMUser 임포트
from users.permissions import IsPMUser

from tasks.models import TaskAssignment, TaskStatusCode
from projects.models import Project
from common.models import CommonCode
from meetings.models import SpecDocument
from requirements.models import RequirementDefinition

# 5단계에서 작성한 Serializer 임포트
from dashboard.serializers import (
    DashboardOverviewResponseSerializer,
    DashboardAnalyticsResponseSerializer,
)


class DashboardOverviewView(APIView):
    """
    GET /api/dashboard/overview/
    대시보드 개요 탭 (PM은 전체 기준, 일반 유저는 본인 업무 기준)
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['0단계 - 대시보드'],
        summary='대시보드 개요 집계 조회',
        description='유저 권한(PM/일반)에 따라 대시보드 요약, 상태 차트, 업무량, 활동 로그, 프로젝트 목록을 집계하여 반환합니다.',
        responses={200: DashboardOverviewResponseSerializer}
    )
    def get(self, request):
        user = request.user
        is_pm = user.is_staff  # 백엔드 단일 기준(is_staff) 적용

        # 2026-09-15: BACKLOG(AI 배분 직후 자동저장된 초안, PM 확정 전)는 PM 화면
        # 포함 대시보드 집계에서 전부 제외한다 — 확정 전 수치는 "진짜" 업무량이
        # 아니고, PM이 검토/수정 중인 화면은 generate_task_suggestions()가 반환한
        # suggestions로 따로 보여주는 게 맞다(대시보드는 그 화면이 아님).
        if is_pm:
            task_qs = TaskAssignment.objects.exclude(status_code_id=TaskStatusCode.BACKLOG)
            project_qs = Project.objects.all()
        else:
            task_qs = TaskAssignment.objects.filter(assigned_user=user).exclude(status_code_id=TaskStatusCode.BACKLOG)
            project_qs = Project.objects.filter(task_assignments__assigned_user=user).distinct()

        # 1. 요약 정보 (summary)
        total_tasks = task_qs.count()
        in_progress = task_qs.filter(status_code__code_id=TaskStatusCode.IN_PROGRESS).count()
        pending_approval = task_qs.filter(status_code__code_id=TaskStatusCode.PENDING_APPROVAL).count()
        done = task_qs.filter(status_code__code_id=TaskStatusCode.COMPLETED).count()
        completion_rate = round((done / total_tasks * 100)) if total_tasks > 0 else 0

        summary = {
            "totalTasks": total_tasks,
            "inProgress": in_progress,
            "pendingApproval": pending_approval,
            "done": done,
            "completionRate": completion_rate
        }

        # 2. 상태 차트 (statusChart)
        status_counts = (
            task_qs.values('status_code__code_id', 'status_code__code_name')
            .annotate(value=Count('id'))
            .order_by()
        )
        status_chart = [
            {
                "code_id": item['status_code__code_id'] or "UNKNOWN",
                "code_name": item['status_code__code_name'] or "미지정",
                "value": item['value']
            }
            for item in status_counts if item['status_code__code_id']
        ]

        # 3. 업무량 (workload)
        # 프로젝트 수가 늘어날수록(테스트/데모 프로젝트 포함) 업무를 한 번이라도
        # 배정받은 적 있는 사람이 계속 늘어나서, 차트에 뜨는 막대 수가 끝없이
        # 늘어나는 문제가 있었다(2026-09-14 확인) — 업무량 상위 TOP_N명만
        # 보여주도록 슬라이스를 추가한다. PM이 "전체 기준"으로 보는 건 그대로
        # 유지하고(회사 전체 집계), 화면에 그릴 막대 개수만 제한한다.
        # 2026-09-15: 직원 수가 많아지면 막대/라벨이 겹친다는 요청으로 7명으로 축소.
        WORKLOAD_TOP_N = 7
        workload = []
        if is_pm:
            workload_data = (
                TaskAssignment.objects.filter(assigned_user__isnull=False)
                .values('assigned_user__id', 'assigned_user__username', 'assigned_user__first_name', 'assigned_user__last_name')
                .annotate(taskCount=Count('id'))
                .order_by('-taskCount')[:WORKLOAD_TOP_N]
            )
            for w in workload_data:
                full_name = f"{w['assigned_user__last_name']}{w['assigned_user__first_name']}".strip() or w['assigned_user__username']
                workload.append({
                    "userId": w['assigned_user__id'],
                    "name": full_name,
                    "taskCount": w['taskCount']
                })

        # 4. 최근 활동 로그 (activityLog)
        recent_tasks = (
            task_qs.select_related('project', 'status_code', 'assigned_user')
            .order_by('-updated_at')[:8]
        )
        activity_log = []
        for task in recent_tasks:
            assignee_name = ""
            if task.assigned_user:
                assignee_name = f"{task.assigned_user.last_name}{task.assigned_user.first_name}".strip() or task.assigned_user.username

            activity_log.append({
                "projectId": task.project.id if task.project else None,
                "projectName": task.project.name if task.project else "",
                "taskTitle": task.title,
                "status": task.status_code.code_id if task.status_code else "",
                "statusLabel": task.status_code.code_name if task.status_code else "",
                "assigneeName": assignee_name,
                "updatedAt": task.updated_at.isoformat() if task.updated_at else None
            })

        # 5. 프로젝트 목록 (projectList)
        project_list = []
        for proj in project_qs:
            proj_tasks = TaskAssignment.objects.filter(project=proj)
            p_total = proj_tasks.count()
            p_done = proj_tasks.filter(status_code__code_id=TaskStatusCode.COMPLETED).count()
            p_progress = round((p_done / p_total * 100)) if p_total > 0 else 0

            project_list.append({
                "id": proj.id,
                "name": proj.name,
                "totalTasks": p_total,
                "doneTasks": p_done,
                "progress": p_progress
            })

        response_data = {
            "summary": summary,
            "statusChart": status_chart,
            "workload": workload,
            "activityLog": activity_log,
            "projectList": project_list
        }
        
        # Serializer 검증을 거친 후 응답
        serializer = DashboardOverviewResponseSerializer(data=response_data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DashboardAnalyticsView(APIView):
    """
    GET /api/dashboard/analytics/
    성과 통계 탭 (PM 전용)
    """
    # IsPMUser 권한 추가 적용
    permission_classes = [permissions.IsAuthenticated, IsPMUser]

    @extend_schema(
        tags=['0단계 - 대시보드'],
        summary='대시보드 성과 통계 조회 (PM 전용)',
        description='최근 7일 완료 추이, 팀원별 기여도, 평균 처리 시간, 승인 통과율, 프로젝트 번다운 현황을 집계합니다.',
        responses={200: DashboardAnalyticsResponseSerializer}
    )
    def get(self, request):
        today = timezone.now().date()

        # 1. 주간 완료 추이 (weeklyCompletion)
        weekly_completion = []
        for i in range(6, -1, -1):
            target_date = today - timedelta(days=i)
            count = TaskAssignment.objects.filter(
                status_code__code_id=TaskStatusCode.COMPLETED,
                updated_at__date=target_date
            ).count()
            weekly_completion.append({
                "date": target_date.strftime("%m-%d"),
                "count": count
            })

        # 2. 팀원별 기여도 (teamContribution)
        # 2026-09-15: 업무를 한 번이라도 배정받은 적 있으면(완료/진행중 건수가 0이어도)
        # 무조건 막대가 하나 생겨서, 인원이 늘수록 의미 없는 빈 막대가 계속 늘어나는
        # 문제가 있었다 — workload 차트의 TOP_N 패턴과 동일하게, 기여(done+inProgress)가
        # 있는 사람만 남기고 기여도 상위 TOP_N명만 보여준다.
        CONTRIBUTION_TOP_N = 10
        team_data = (
            TaskAssignment.objects.filter(assigned_user__isnull=False)
            .values('assigned_user__id', 'assigned_user__username', 'assigned_user__first_name', 'assigned_user__last_name')
            .annotate(
                done=Count('id', filter=Q(status_code__code_id=TaskStatusCode.COMPLETED)),
                inProgress=Count('id', filter=Q(status_code__code_id=TaskStatusCode.IN_PROGRESS))
            )
            .filter(Q(done__gt=0) | Q(inProgress__gt=0))
            .order_by('-done', '-inProgress')[:CONTRIBUTION_TOP_N]
        )
        team_contribution = []
        for t in team_data:
            name = f"{t['assigned_user__last_name']}{t['assigned_user__first_name']}".strip() or t['assigned_user__username']
            team_contribution.append({
                "name": name,
                "done": t['done'],
                "inProgress": t['inProgress']
            })

        # 3. 평균 처리 시간 (averageProcessTime)
        completed_tasks = TaskAssignment.objects.filter(
            status_code__code_id=TaskStatusCode.COMPLETED,
            created_at__isnull=False,
            updated_at__isnull=False
        ).annotate(
            duration=ExpressionWrapper(F('updated_at') - F('created_at'), output_field=fields.DurationField())
        )

        avg_duration = completed_tasks.aggregate(avg_time=Avg('duration'))['avg_time']
        if avg_duration:
            average_process_time = round(avg_duration.total_seconds() / 86400, 1)
        else:
            average_process_time = 0.0

        # 4. 승인 통과율 (approvalPassRate)
        # 2026-09-15: 지금까지는 TaskAssignment(개별 업무) 기준으로만 집계해서
        # "승인 8건·반려 0건"처럼 뭉뚱그려 보였고, 정작 승인/반려가 실제로 일어나는
        # 기획서·요구사항정의서 단계별로는 몇 건인지 알 수 없었다(사용자 요청 —
        # "대체 몇 건을 승인했고 몇 건을 반려했는지 전혀 모르겠다"). 문서 종류별로
        # 나눠서 집계한다(develop에서 병합된 TaskAssignment 기준 approved_count/
        # rejected_count는 이 방식으로 대체되어 더 안 쓴다).
        proposal_approved = SpecDocument.objects.filter(status_code__code_id='PROPOSAL_APPROVED').count()
        proposal_rejected = SpecDocument.objects.filter(status_code__code_id='PROPOSAL_REJECTED').count()
        requirement_approved = RequirementDefinition.objects.filter(status_code__code_id='APPROVED').count()
        requirement_rejected = RequirementDefinition.objects.filter(status_code__code_id='REJECTED').count()

        approval_pass_rate = {
            "proposal": {"approved": proposal_approved, "rejected": proposal_rejected},
            "requirement": {"approved": requirement_approved, "rejected": requirement_rejected},
        }

        # 5. 프로젝트 번다운 (projectBurndown)
        project_burndown = []
        projects = Project.objects.all()
        for proj in projects:
            remaining_count = TaskAssignment.objects.filter(
                project=proj,
                status_code__code_id__in=[
                    TaskStatusCode.PENDING_APPROVAL,
                    TaskStatusCode.IN_PROGRESS
                ]
            ).count()
            project_burndown.append({
                "name": proj.name,
                "remaining": remaining_count
            })

        response_data = {
            "weeklyCompletion": weekly_completion,
            "teamContribution": team_contribution,
            "averageProcessTime": average_process_time,
            "approvalPassRate": approval_pass_rate,
            "projectBurndown": project_burndown
        }

        serializer = DashboardAnalyticsResponseSerializer(data=response_data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
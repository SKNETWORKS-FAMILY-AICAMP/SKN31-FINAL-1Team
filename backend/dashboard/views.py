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

        if is_pm:
            task_qs = TaskAssignment.objects.all()
            project_qs = Project.objects.all()
        else:
            task_qs = TaskAssignment.objects.filter(assigned_user=user)
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
        workload = []
        if is_pm:
            workload_data = (
                TaskAssignment.objects.filter(assigned_user__isnull=False)
                .values('assigned_user__id', 'assigned_user__username', 'assigned_user__first_name', 'assigned_user__last_name')
                .annotate(taskCount=Count('id'))
                .order_by('-taskCount')
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
        team_data = (
            TaskAssignment.objects.filter(assigned_user__isnull=False)
            .values('assigned_user__id', 'assigned_user__username', 'assigned_user__first_name', 'assigned_user__last_name')
            .annotate(
                done=Count('id', filter=Q(status_code__code_id=TaskStatusCode.COMPLETED)),
                inProgress=Count('id', filter=Q(status_code__code_id=TaskStatusCode.IN_PROGRESS))
            )
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
        approved_count = TaskAssignment.objects.filter(
            status_code__code_id__in=[
                TaskStatusCode.APPROVED,
                TaskStatusCode.IN_PROGRESS,
                TaskStatusCode.COMPLETED
            ]
        ).count()
        rejected_count = TaskAssignment.objects.filter(
            status_code__code_id=TaskStatusCode.REJECTED
        ).count()

        approval_pass_rate = {
            "approved": approved_count,
            "rejected": rejected_count
        }

        # 5. 프로젝트 번다운 (projectBurndown)
        project_burndown = []
        projects = Project.objects.all()
        for proj in projects:
            remaining_count = TaskAssignment.objects.filter(
                project=proj,
                status_code__code_id__in=[
                    TaskStatusCode.PENDING_APPROVAL,
                    TaskStatusCode.APPROVED,
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
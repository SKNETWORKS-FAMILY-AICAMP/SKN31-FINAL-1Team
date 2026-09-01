#tasks/views.py
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiTypes,
    OpenApiResponse,
)

from tasks.models import TaskAssignment
from tasks.serializers import (
    TaskAssignmentSerializer,
    TaskAssignmentCreateSerializer,
    TaskStatusUpdateSerializer,
)
from requirements.models import RequirementItem
from projects.models import PipelineHistory, Project
from notifications.services import notify_user

User = get_user_model()


@extend_schema_view(
    get=extend_schema(
        tags=['3단계 - 업무 배정'],
        summary='배정 업무 목록 조회',
        description='등록된 전체 배정 업무 목록을 조회합니다.',
        responses={200: TaskAssignmentSerializer(many=True)}
    ),
    post=extend_schema(
        tags=['3단계 - 업무 배정'],
        summary='업무 수동 배정',
        description='요구사항 항목에 대해 특정 개발자에게 업무를 수동으로 배정합니다.',
        request=TaskAssignmentCreateSerializer,
        responses={201: TaskAssignmentCreateSerializer}
    )
)
class TaskAssignmentListCreateView(generics.ListCreateAPIView):
    """
    배정 업무 목록 조회 및 수동 생성 API
    GET/POST /api/tasks/assignments/
    """
    queryset = TaskAssignment.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return TaskAssignmentCreateSerializer
        return TaskAssignmentSerializer

    # 프론트(칸반보드/프로젝트 상세)가 "이 프로젝트의 업무만", "이 담당자 업무만" 같은 필터링을
    # 필요로 하는데, TaskAssignment에는 project 필드가 없다 — 대신 req_item -> req_def -> spec
    # -> meeting -> project로 이어지는 체인을 타고 내려가서 필터링한다.
    def get_queryset(self):
        qs = TaskAssignment.objects.all()
        project_id = self.request.query_params.get('project')
        assignee_id = self.request.query_params.get('assigneeId')
        status_param = self.request.query_params.get('status')
        if project_id:
            qs = qs.filter(req_item__req_def__spec__meeting__project_id=project_id)
        if assignee_id:
            qs = qs.filter(assigned_user_id=assignee_id)
        if status_param:
            qs = qs.filter(status=status_param)
        return qs


@extend_schema_view(
    get=extend_schema(
        tags=['3단계 - 업무 배정'],
        summary='배정 업무 상세 조회',
        description='특정 배정 업무의 상세 정보를 조회합니다.',
        responses={200: TaskAssignmentSerializer}
    ),
    put=extend_schema(
        tags=['3단계 - 업무 배정'],
        summary='배정 업무 전체 수정',
        description='특정 배정 업무의 전체 정보를 수정합니다.',
        responses={200: TaskAssignmentSerializer}
    ),
    patch=extend_schema(
        tags=['3단계 - 업무 배정'],
        summary='배정 업무 부분 수정',
        description='특정 배정 업무의 일부 정보를 수정합니다.',
        responses={200: TaskAssignmentSerializer}
    ),
    delete=extend_schema(
        tags=['3단계 - 업무 배정'],
        summary='배정 업무 삭제',
        description='특정 배정 업무를 삭제합니다.',
        responses={204: None}
    )
)
class TaskAssignmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    배정 업무 상세 조회 / 수정 / 삭제 API
    GET/PUT/PATCH/DELETE /api/tasks/assignments/{id}/
    """
    queryset = TaskAssignment.objects.all()
    serializer_class = TaskAssignmentSerializer
    permission_classes = [permissions.IsAuthenticated]


class AutoTaskAssignView(APIView):
    """
    개발자 작업 상태(is_busy) 및 스킬 기반 업무 AI 자동 배정 API
    POST /api/tasks/auto-assign/
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['3단계 - 업무 배정'],
        summary='업무 AI 자동 배정',
        description='요구사항 항목(`req_item_id`)을 확인하여 가용한 개발자(`is_busy=False`)에게 업무를 자동 배정합니다. 배정 시 해당 개발자의 `is_busy` 상태가 `True`로 변경되며, `project_id` 포함 시 `PipelineHistory` 타임라인 이력이 기록됩니다.',
        responses={
            201: OpenApiResponse(
                description='업무 자동 배정 완료',
                response=TaskAssignmentSerializer
            ),
            400: OpenApiResponse(description='가용한 유저가 없거나 요청 값이 잘못됨'),
            404: OpenApiResponse(description='요구사항 항목 또는 프로젝트를 찾을 수 없음')
        }
    )
    def post(self, request):
        req_item_id = request.data.get('req_item_id')
        project_id = request.data.get('project_id')
        
        req_item = get_object_or_404(RequirementItem, pk=req_item_id)

        # 현재 작업 중이지 않은(is_busy=False) 개발자 선별
        available_users = User.objects.filter(is_active=True, is_busy=False)
        
        if not available_users.exists():
            # 가용한 개발자가 없을 경우 전체 유저 중 무작위/첫 번째 유저 매핑
            assigned_user = User.objects.filter(is_active=True).first()
        else:
            assigned_user = available_users.first()

        if not assigned_user:
            return Response({"error": "배정할 수 있는 유저가 시스템에 존재하지 않습니다."}, status=status.HTTP_400_BAD_REQUEST)

        # 업무 생성
        task = TaskAssignment.objects.create(
            req_item=req_item,
            assigned_user=assigned_user,
            task_title=f"[{req_item.req_code}] {req_item.req_name} 개발",
            task_description=req_item.description,
            status=TaskAssignment.Status.PENDING_APPROVAL
        )

        # 개발자 작업중 상태 업데이트
        assigned_user.is_busy = True
        assigned_user.save()

        # 파이프라인 이력 로그 생성
        if project_id:
            project = get_object_or_404(Project, pk=project_id)
            PipelineHistory.objects.create(
                project=project,
                requirement=req_item.req_def,
                task=task,
                step_type='TASK_ASSIGNED',
                title=f"업무 자동 배정: {task.task_title}",
                description=f"담당자: {assigned_user.username} 사원 (승인 대기)",
                actor=request.user
            )

        return Response({
            "message": "개발자에게 업무가 성공적으로 자동 배정되었습니다.",
            "task": TaskAssignmentSerializer(task).data
        }, status=status.HTTP_201_CREATED)


class TaskStatusUpdateView(APIView):
    """
    업무 승인 및 상태 변경 API
    PATCH /api/tasks/assignments/{id}/status/
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['3단계 - 업무 배정'],
        summary='업무 승인 및 상태 변경',
        description='배정된 업무의 진행 상태(`status`)를 변경합니다. 상태가 `COMPLETED`(완료)로 변경되면 담당 개발자의 `is_busy` 상태가 `False`로 해제되어 다음 업무를 배정받을 수 있게 됩니다.',
        parameters=[
            OpenApiParameter(
                name='pk',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description='상태를 변경할 배정 업무 ID'
            )
        ],
        request=TaskStatusUpdateSerializer,
        responses={
            200: OpenApiResponse(
                description='업무 상태 변경 완료',
                response=TaskAssignmentSerializer
            ),
            400: OpenApiResponse(description='유효하지 않은 status 값'),
            404: OpenApiResponse(description='존재하지 않는 배정 업무')
        }
    )
    def patch(self, request, pk):
        task = get_object_or_404(TaskAssignment, pk=pk)
        new_status = request.data.get('status')

        if new_status not in TaskAssignment.Status.values:
            return Response({"error": "유효하지 않은 status 값입니다."}, status=status.HTTP_400_BAD_REQUEST)

        # 반려는 승인 대기 상태에서만 사유와 함께 — 담당자를 다시 배정 없이 그냥 되돌리면
        # 사유가 안 남아 왜 반려됐는지 알 방법이 없다.
        if new_status == TaskAssignment.Status.REJECTED:
            reason = request.data.get('reject_reason', '').strip()
            if not reason:
                return Response({"error": "반려 사유를 입력해주세요."}, status=status.HTTP_400_BAD_REQUEST)
            task.reject_reason = reason
        elif new_status != task.status:
            task.reject_reason = None

        task.status = new_status
        task.save()

        # 업무가 완료(COMPLETED)되면 개발자의 is_busy 해제
        if new_status == TaskAssignment.Status.COMPLETED:
            user = task.assigned_user
            user.is_busy = False
            user.save()

        # 담당자에게 승인/반려 결과를 알린다 (검토요청/승인/반려 알림 패턴과 동일)
        if new_status == TaskAssignment.Status.APPROVED:
            notify_user(task.assigned_user, f"'{task.task_title}' 업무가 승인되었습니다.", type='success', link='/tasks')
        elif new_status == TaskAssignment.Status.REJECTED:
            notify_user(task.assigned_user, f"'{task.task_title}' 업무가 반려되었습니다: {task.reject_reason}", type='error', link='/tasks')

        return Response({
            "message": "업무 상태가 성공적으로 변경되었습니다.",
            "task": TaskAssignmentSerializer(task).data
        }, status=status.HTTP_200_OK)
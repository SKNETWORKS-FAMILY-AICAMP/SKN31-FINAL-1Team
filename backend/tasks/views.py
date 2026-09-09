#tasks/views.py
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiTypes,
    OpenApiResponse,
)

from tasks.models import TaskAssignment, TaskStatusCode
from tasks.serializers import (
    TaskAssignmentSerializer,
    TaskAssignmentCreateSerializer,
    TaskStatusUpdateSerializer,
)
# services.py에서 구현되어 있는 AI 로직 함수 임포트
from tasks.services import run_assignee_mapping, run_task_generation
from requirements.models import RequirementItem
from projects.models import PipelineHistory, Project
from notifications.services import notify_user

User = get_user_model()


@extend_schema_view(
    get=extend_schema(
        tags=['3단계 - 업무 배정'],
        summary='배정 업무 목록 조회',
        description='등록된 전체 배정 업무 목록을 조회합니다. 프로젝트 ID, 담당자 ID, 상태 코드를 통한 필터링이 가능합니다.',
        parameters=[
            OpenApiParameter(
                name='project',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='프로젝트 ID (Project ID)로 필터링',
                required=False
            ),
            OpenApiParameter(
                name='assigneeId',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='담당자 유저 ID (User ID)로 필터링',
                required=False
            ),
            OpenApiParameter(
                name='status',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='업무 상태 코드 (TaskStatusCode)로 필터링',
                required=False
            ),
        ],
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
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return TaskAssignmentCreateSerializer
        return TaskAssignmentSerializer

    # 프론트(칸반보드/프로젝트 상세)가 "이 프로젝트의 업무만", "이 담당자 업무만" 같은 필터링을
    # 필요로 하는데, TaskAssignment에는 project 필드가 없다 — 대신 req_item -> req_def -> spec
    # -> meeting -> project로 이어지는 체인을 타고 내려가서 필터링한다.
    def get_queryset(self):
        qs = TaskAssignment.objects.select_related(
            'req_item', 
            'assigned_user', 
            'status_code'
        ).all()
        project_id = self.request.query_params.get('project')
        assignee_id = self.request.query_params.get('assigneeId')
        status_param = self.request.query_params.get('status')
        if project_id:
            qs = qs.filter(req_item__req_def__spec__meeting__project_id=project_id)
        if assignee_id:
            qs = qs.filter(assigned_user_id=assignee_id)
        if status_param:
            qs = qs.filter(status_code_id=status_param)
        return qs


@extend_schema_view(
    get=extend_schema(
        tags=['3단계 - 업무 배정'],
        summary='배정 업무 상세 조회',
        description='특정 배정 업무의 상세 정보를 조회합니다.',
        parameters=[
            OpenApiParameter(
                name='id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description='조회할 배정 업무 ID'
            )
        ],
        responses={200: TaskAssignmentSerializer}
    ),
    put=extend_schema(
        tags=['3단계 - 업무 배정'],
        summary='배정 업무 전체 수정',
        description='특정 배정 업무의 전체 정보를 수정합니다.',
        parameters=[
            OpenApiParameter(
                name='id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description='수정할 배정 업무 ID'
            )
        ],
        responses={200: TaskAssignmentSerializer}
    ),
    patch=extend_schema(
        tags=['3단계 - 업무 배정'],
        summary='배정 업무 부분 수정',
        description='특정 배정 업무의 일부 정보를 수정합니다.',
        parameters=[
            OpenApiParameter(
                name='id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description='수정할 배정 업무 ID'
            )
        ],
        responses={200: TaskAssignmentSerializer}
    ),
    delete=extend_schema(
        tags=['3단계 - 업무 배정'],
        summary='배정 업무 삭제',
        description='특정 배정 업무를 삭제합니다.',
        parameters=[
            OpenApiParameter(
                name='id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description='삭제할 배정 업무 ID'
            )
        ],
        responses={204: None}
    )
)
class TaskAssignmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    배정 업무 상세 조회 / 수정 / 삭제 API
    GET/PUT/PATCH/DELETE /api/tasks/assignments/{id}/
    """
    queryset = TaskAssignment.objects.select_related('req_item', 'assigned_user', 'status_code').all()
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
    @transaction.atomic
    def post(self, request):
        req_item_id = request.data.get('req_item_id')
        project_id = request.data.get('project_id')
        
        req_item = get_object_or_404(RequirementItem, pk=req_item_id)

        # 현재 작업 중이지 않은(is_busy=False) 개발자 선별 및 동시성 락 적용
        available_users = User.objects.select_for_update().filter(is_active=True, is_busy=False)
        
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
            project_id=project_id or req_item.req_def.project_id,
            title=f"[{req_item.req_code}] {req_item.req_name} 개발",
            description=req_item.description,
            status_code_id=TaskStatusCode.PENDING_APPROVAL,
        )

        # 개발자 작업중 상태 업데이트
        assigned_user.is_busy = True
        assigned_user.save()

        notify_user(assigned_user, f"'{task.title}' 업무가 배정되었습니다.", type='info', link='/tasks')

        # 파이프라인 이력 로그 생성
        if project_id:
            project = get_object_or_404(Project, pk=project_id)
            PipelineHistory.objects.create(
                project=project,
                requirement=req_item.req_def,
                task=task,
                step_type='TASK_ASSIGNED',
                title=f"업무 자동 배정: {task.title}",
                description=f"담당자: {assigned_user.username} 사원 (승인 대기)",
                actor=request.user
            )

        return Response({
            "message": "개발자에게 업무가 성공적으로 자동 배정되었습니다.",
            "task": TaskAssignmentSerializer(task).data
        }, status=status.HTTP_201_CREATED)

#tasks/views.py
class TaskStatusUpdateView(APIView):
    """
    업무 승인, 상태 변경 및 담당자 변경 API
    PATCH /api/tasks/assignments/{id}/status/
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['3단계 - 업무 배정'],
        summary='업무 승인, 상태 변경 및 담당자 변경',
        description=(
            '배정된 업무의 진행 상태(`status_code`) 및 담당자(`assigned_user_id`)를 변경합니다.\n'
            '- **담당자 변경**: PM만 수행할 수 있습니다.\n'
            '- **상태 변경**: PM 또는 해당 업무의 담당자 본인(`assigned_user`)만 수행할 수 있습니다.\n'
            '- 상태가 `COMPLETED`로 변경되면 담당 개발자의 `is_busy` 상태가 `False`로 해제됩니다.'
        ),
        parameters=[
            OpenApiParameter(
                name='id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description='상태를 변경할 배정 업무 ID'
            )
        ],
        request=TaskStatusUpdateSerializer,
        responses={
            200: OpenApiResponse(
                description='업무 상태/담당자 변경 완료',
                response=TaskAssignmentSerializer
            ),
            400: OpenApiResponse(description='유효하지 않은 요청 파라미터'),
            403: OpenApiResponse(description='권한 없음 (PM이 아니거나 본인 업무가 아님)'),
            404: OpenApiResponse(description='존재하지 않는 배정 업무')
        }
    )
    @transaction.atomic
    def patch(self, request, pk):
        task = get_object_or_404(TaskAssignment, pk=pk)
        user = request.user
        is_pm = getattr(user, 'is_staff', False) or user.groups.filter(name='PM').exists()

        new_status = request.data.get('status_code') or request.data.get('status')
        new_assignee_id = request.data.get('assigned_user_id') or request.data.get('assigned_user')

        # ------------------------------------------------------------------
        # 1. 담당자 변경 (Assignee Change) 권한 검증
        # ------------------------------------------------------------------
        if new_assignee_id and int(new_assignee_id) != task.assigned_user_id:
            if not is_pm:
                return Response(
                    {"error": "FORBIDDEN", "details": "담당자 재배정은 PM 권한이 필요합니다."},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            new_assignee = get_object_or_404(User, pk=new_assignee_id)
            
            # 기존 담당자 is_busy 해제 (해당 개발자가 수행 중인 다른 업무가 없는 경우)
            old_assignee = task.assigned_user
            if old_assignee:
                other_busy_tasks = TaskAssignment.objects.filter(
                    assigned_user=old_assignee
                ).exclude(pk=task.pk).exclude(status_code_id=TaskStatusCode.COMPLETED)
                if not other_busy_tasks.exists():
                    old_assignee.is_busy = False
                    old_assignee.save()

            # 새 담당자 지정 및 is_busy 설정
            task.assigned_user = new_assignee
            new_assignee.is_busy = True
            new_assignee.save()

            notify_user(new_assignee, f"'{task.title}' 업무의 새로운 담당자로 지정되었습니다.", type='info', link='/tasks')

        # ------------------------------------------------------------------
        # 2. 업무 카드 상태 변경 (Status Transition) 권한 검증
        # ------------------------------------------------------------------
        if new_status:
            if new_status not in TaskStatusCode.VALUES:
                return Response(
                    {"error": "INVALID_STATUS", "details": "유효하지 않은 status_code 값입니다."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # ── [추가/수정] 상태별 세부 권한 분기 ────────────────────────────
            # A. 배분 승인(APPROVED) / 반려(REJECTED)는 PM만 가능
            if new_status in [TaskStatusCode.APPROVED, TaskStatusCode.REJECTED]:
                if not is_pm:
                    return Response(
                        {"error": "FORBIDDEN", "details": "업무 배분 승인 및 반려는 PM 권한이 필요합니다."},
                        status=status.HTTP_403_FORBIDDEN
                    )

            # B. 기타 상태 변경(IN_PROGRESS, COMPLETED 등)은 PM 또는 담당자 본인만 가능
            else:
                if not is_pm and task.assigned_user_id != user.id:
                    return Response(
                        {"error": "FORBIDDEN", "details": "본인에게 배정된 업무만 상태를 변경할 수 있습니다."},
                        status=status.HTTP_403_FORBIDDEN
                    )
            # ─────────────────────────────────────────────────────────────

            old_status = task.status_code_id

            # 반려 처리 시 사유 검증
            if new_status == TaskStatusCode.REJECTED:
                reason = request.data.get('reject_reason', '').strip()
                if not reason:
                    return Response({"error": "REQUIRED_REASON", "details": "반려 사유를 입력해주세요."}, status=status.HTTP_400_BAD_REQUEST)
                task.reject_reason = reason
            elif new_status != old_status:
                task.reject_reason = None

            task.status_code_id = new_status

            # 업무 완료(COMPLETED) 시 담당 개발자 is_busy 해제
            if new_status == TaskStatusCode.COMPLETED:
                assigned_dev = task.assigned_user
                if assigned_dev:
                    other_busy_tasks = TaskAssignment.objects.filter(
                        assigned_user=assigned_dev
                    ).exclude(pk=task.pk).exclude(status_code_id=TaskStatusCode.COMPLETED)
                    if not other_busy_tasks.exists():
                        assigned_dev.is_busy = False
                        assigned_dev.save()

            # 알림 발송
            if new_status == TaskStatusCode.APPROVED and task.assigned_user:
                notify_user(task.assigned_user, f"'{task.title}' 업무가 승인되었습니다.", type='success', link='/tasks')
            elif new_status == TaskStatusCode.REJECTED and task.assigned_user:
                notify_user(task.assigned_user, f"'{task.title}' 업무가 반려되었습니다: {task.reject_reason}", type='error', link='/tasks')

            # 파이프라인 히스토리 기록 (실제 상태가 변경된 경우)
            if task.project_id and new_status != old_status:
                if new_status == TaskStatusCode.APPROVED:
                    PipelineHistory.objects.create(
                        project=task.project,
                        task=task,
                        step_type='TASK_IN_PROGRESS',
                        title=f"업무 진행 시작: {task.title}",
                        description=f"담당자: {task.assigned_user.username if task.assigned_user else '미정'}",
                        actor=user,
                    )
                elif new_status == TaskStatusCode.COMPLETED:
                    PipelineHistory.objects.create(
                        project=task.project,
                        task=task,
                        step_type='COMPLETED',
                        title=f"업무 완료: {task.title}",
                        description=f"담당자: {task.assigned_user.username if task.assigned_user else '미정'}",
                        actor=user,
                    )

        task.save()

        return Response({
            "message": "업무 정보가 성공적으로 변경되었습니다.",
            "task": TaskAssignmentSerializer(task).data
        }, status=status.HTTP_200_OK)


class AIAssigneeMappingView(APIView):
    """
    AI 담당자 매핑 API
    POST /api/tasks/ai/assignee-mapping/ (또는 /api/ai/assignee-mapping/)
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['3단계 - 업무 배정'],
        summary='AI 담당자 매핑 추천',
        description='AI 알고리즘을 활용하여 업무 요구사항에 가장 적합한 담당자 매핑 결과를 추천받습니다.',
        responses={200: OpenApiResponse(description='AI 담당자 매핑 성공')}
    )
    def post(self, request):
        result = run_assignee_mapping(request.data)
        return Response(result, status=status.HTTP_200_OK)


class AITaskGenerationView(APIView):
    """
    AI 업무 생성 API
    POST /api/tasks/ai/task-generation/ (또는 /api/ai/task-generation/)
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['3단계 - 업무 배정'],
        summary='AI 업무 자동 생성',
        description='요구사항 명세서를 바탕으로 AI가 구체적인 업무 목록을 자동 생성합니다.',
        responses={200: OpenApiResponse(description='AI 업무 생성 성공')}
    )
    def post(self, request):
        result = run_task_generation(request.data)
        return Response(result, status=status.HTTP_200_OK)
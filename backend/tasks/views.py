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
    _is_resigned,
)
from projects.models import PipelineHistory
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
        # 2026-09-16: BACKLOG(AI 배분 직후 자동저장된 초안, 아직 아무도 검토 전)는
        # PM 확인 전까지 아무한테도 안 보여야 한다 — 예전엔 PM만 예외로 뒀었는데,
        # 실제로 PM이 초안을 검토/수정하는 화면(documents/page.tsx)은 이 목록 API를
        # 다시 불러오지 않고 generate_task_suggestions()가 그 자리에서 반환한 값을
        # 그대로 쓴다. 즉 이 엔드포인트로 BACKLOG를 보여줄 실사용처가 없어 — PM이
        # "업무관리"를 열면 검토 안 된 AI 초안이 실제 배정 목록에 섞여 보이기만 했다.
        # ?status=BACKLOG를 명시적으로 요청한 PM에게만 예외로 허용한다(향후 필요해질
        # 진단/확인 용도 대비 — 지금은 이걸 쓰는 화면이 없다).
        is_pm = getattr(self.request.user, 'is_staff', False) or self.request.user.groups.filter(name='PM').exists()
        if not (is_pm and status_param == TaskStatusCode.BACKLOG):
            qs = qs.exclude(status_code_id=TaskStatusCode.BACKLOG)
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
    serializer_class = TaskAssignmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # 2026-09-16: id를 직접 안다고 해도 BACKLOG(초안)는 상세 조회/수정/삭제로
        # 못 보게 막는다 — 목록 API와 동일하게 PM도 예외 없이 막는다(TaskAssignmentListCreateView
        # 참고: PM이 초안을 검토/수정하는 화면은 이 REST 엔드포인트를 아예 안 쓴다).
        return TaskAssignment.objects.select_related(
            'req_item', 'assigned_user', 'status_code'
        ).exclude(status_code_id=TaskStatusCode.BACKLOG)


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
            '- 상태가 `DONE`으로 변경되면 담당 개발자의 `is_busy` 상태가 `False`로 해제됩니다.'
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
            # 2026-09-16 (사용자 요청): 담당자가 배정을 승인했거나(TASK_APPROVED) 이미
            # 착수한(IN_PROGRESS) 업무는 담당자를 바꿔치기할 수 없다 — TaskAssignmentSerializer
            # 쪽과 동일한 제약을 이 엔드포인트에도 건다.
            # 2026-09-16 (잠금 예외): 현재 담당자가 이미 퇴사 처리됐으면, 이 잠금 때문에
            # 그 업무가 영영 재배정 못 하고 붕 떠버린다 — 상태와 무관하게 허용. 퇴사 처리
            # 경로가 두 가지라(목록 빠른 변경은 status_code만, 수정 모달은 resign_date도
            # 같이 보냄 — 실측 확인) _is_resigned()가 둘 다 확인한다.
            current_assignee_resigned = _is_resigned(task.assigned_user)
            if (
                task.status_code_id in (TaskStatusCode.APPROVED, TaskStatusCode.IN_PROGRESS, TaskStatusCode.COMPLETED)
                and not current_assignee_resigned
            ):
                return Response(
                    {"error": "FORBIDDEN", "details": "승인·진행 중이거나 완료된 업무는 담당자를 변경할 수 없습니다."},
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

            # 2026-09-16 (사용자 지적): assignment_reason은 AI가 원래 추천했던 담당자를
            # 기준으로 판단한 근거라, PM이 다른 사람으로 재배정하면 새 담당자한테 안 맞는
            # 말이 된다 — TaskAssignmentSerializer.update()와 동일하게 정직한 안내 문구로
            # 대체한다(재계산은 하지 않음 — 비용·일관성 문제로 이전에 보류 결정). 다만 원래
            # (AI 최초 추천) 담당자로 다시 되돌리는 경우엔 지워졌던 원래 근거를 복원한다.
            if task.original_assigned_user_id is not None and new_assignee.pk == task.original_assigned_user_id:
                task.assignment_reason = task.original_assignment_reason
            else:
                note = "PM이 직접 재배정한 담당자입니다 (AI 추천 근거 아님)"
                task.assignment_reason = f"{note} / {note} / {note}"

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

            # ── 상태별 세부 권한 분기 ────────────────────────────────────
            # 2026-09-22 (사용자 재확인 — 9/16 정책으로 재복귀): 배분 승인(APPROVED)/
            # 반려(REJECTED)는 PM이 배분하는 액션이 아니라, PM이 배정한 업무를 담당자
            # 본인이 받아들일지 정하는 액션이다 — 그래서 PM 전용이었던 예외(9/18)를
            # 없애고, 다른 상태 변경(B)과 동일하게 "PM 또는 담당자 본인"으로 통일한다.
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
            elif new_status == TaskStatusCode.COMPLETED and task.assigned_user:
                notify_user(task.assigned_user, f"'{task.title}' 업무가 완료되었습니다.", type='success', link='/tasks')
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
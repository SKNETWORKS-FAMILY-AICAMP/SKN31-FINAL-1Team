from django.shortcuts import render
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from drf_spectacular.utils import extend_schema, extend_schema_view  # 추가된 부분

from .models import TaskAssignment
from .serializers import TaskAssignmentSerializer
from .notifications import send_task_assignment_notification


@extend_schema_view(
    list=extend_schema(summary="업무 배정 목록 조회"),
    create=extend_schema(summary="업무 배정 생성"),
    retrieve=extend_schema(summary="업무 배정 상세 조회"),
    update=extend_schema(summary="업무 배정 전체 수정"),
    partial_update=extend_schema(summary="업무 배정 부분 수정"),
    destroy=extend_schema(summary="업무 배정 삭제"),
)
class TaskAssignmentViewSet(viewsets.ModelViewSet):
    queryset = TaskAssignment.objects.all().order_by('-created_at')
    serializer_class = TaskAssignmentSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="승인 대기 업무 배정 목록 조회")
    @action(detail=False, methods=['get'], url_path='pending')
    def pending_assignments(self, request):
        """
        승인 대기(PENDING_APPROVAL) 중인 업무 배정 목록 조회
        """
        pending_tasks = self.queryset.filter(status=TaskAssignment.Status.PENDING_APPROVAL)
        serializer = self.get_serializer(pending_tasks, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(summary="업무 배정 최종 승인 및 사원 알림 전송")
    @action(detail=False, methods=['post'], url_path='approve-all')
    def approve_and_notify(self, request):
        """
        3-1. 업무 배분 검토 (팀장 승인 버튼 > 개별 사원 알림 API)
        - 선택된(또는 대기 중인) 업무 배분안을 최종 승인(APPROVED) 처리
        - 배정된 사원들의 상태를 is_busy = True로 업데이트
        - 각 사원에게 개별 알림 전송
        """
        # 요청 바디에서 승인할 task_ids 목록을 받거나, 전체 대기 항목을 승인 처리
        task_ids = request.data.get('task_ids', [])
        
        if task_ids:
            tasks_to_approve = TaskAssignment.objects.filter(
                id__in=task_ids, 
                status=TaskAssignment.Status.PENDING_APPROVAL
            )
        else:
            tasks_to_approve = TaskAssignment.objects.filter(
                status=TaskAssignment.Status.PENDING_APPROVAL
            )

        if not tasks_to_approve.exists():
            return Response(
                {"detail": "승인할 대기 상태의 업무가 없습니다."},
                status=status.HTTP_400_BAD_REQUEST
            )

        approved_count = 0
        
        # 트랜잭션으로 상태 업데이트 및 알림 처리의 일관성 보장
        with transaction.atomic():
            for task in tasks_to_approve:
                # 1. 업무 상태를 '승인 완료'로 변경
                task.status = TaskAssignment.Status.APPROVED
                task.save()

                # 2. 담당 사원의 작업 상태를 작업 중(is_busy = True)으로 변경
                assigned_user = task.assigned_user
                assigned_user.is_busy = True
                assigned_user.save()

                # 3. 개별 사원에게 알림 전송
                send_task_assignment_notification(task)
                
                approved_count += 1

        return Response(
            {
                "message": f"총 {approved_count}건의 업무 배분이 최종 승인되었으며, 담당 사원들에게 알림이 발송되었습니다.",
                "approved_count": approved_count
            },
            status=status.HTTP_200_OK
        )
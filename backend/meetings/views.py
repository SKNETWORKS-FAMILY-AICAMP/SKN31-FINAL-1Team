from django.shortcuts import render

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import MeetingNote
from .serializers import MeetingNoteSerializer
from specs.tasks import generate_spec_from_meeting  # 기획서 생성 태스크


@extend_schema_view(
    list=extend_schema(summary="회의록 목록 조회", tags=["회의록"]),
    create=extend_schema(summary="회의록 작성/저장", tags=["회의록"]),
    retrieve=extend_schema(summary="회의록 상세 조회", tags=["회의록"]),
    update=extend_schema(summary="회의록 전체 수정", tags=["회의록"]),
    partial_update=extend_schema(summary="회의록 부분 수정", tags=["회의록"]),
    destroy=extend_schema(summary="회의록 삭제", tags=["회의록"]),
)
class MeetingNoteViewSet(viewsets.ModelViewSet):
    queryset = MeetingNote.objects.all().order_by('-created_at')
    serializer_class = MeetingNoteSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        # 작성자를 현재 로그인한 유저로 자동 저장
        serializer.save(created_by=self.request.user)

    @extend_schema(
        tags=["회의록"],
        summary="1-1. 회의록 검토 완료 처리",
        description="회의록 상태를 REVIEWED로 변경하고, 백그라운드 태스크를 호출해 기획서 자동 생성을 시작합니다.",
        request=None,  # POST 요청 시 추가 Body 데이터가 없음을 명시
        responses={
            200: OpenApiResponse(
                description="검토 완료 성공 및 기획서 생성 시작",
                response=MeetingNoteSerializer
            ),
            400: OpenApiResponse(
                description="이미 검토 완료된 회의록인 경우"
            ),
        }
    )
    @action(detail=True, methods=['post'], url_path='review-complete')
    def review_complete(self, request, pk=None):
        """
        1-1. 회의록 검토 완료 버튼 클릭 시 호출
        - 회의록 상태를 REVIEWED로 변경
        - 기획서 자동 작성 API/서비스 호출
        """
        meeting = self.get_object()

        # 이미 검토 완료된 경우 예외 처리
        if meeting.status == MeetingNote.Status.REVIEWED:
            return Response(
                {"detail": "이미 검토 완료된 회의록입니다."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 1. 회의록 상태 변경
        meeting.status = MeetingNote.Status.REVIEWED
        meeting.save()

        # 2. 기획서 생성 비동기 처리 API/서비스 호출
        # (Celery 적용 시 generate_spec_from_meeting.delay(meeting.id)로 호출)
        generate_spec_from_meeting(meeting.id)

        serializer = self.get_serializer(meeting)
        return Response(
            {
                "message": "회의록 검토가 완료되었으며, 기획서 자동 생성이 시작되었습니다.",
                "data": serializer.data
            },
            status=status.HTTP_200_OK
        )
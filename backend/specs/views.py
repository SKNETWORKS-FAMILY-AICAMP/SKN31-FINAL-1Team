from django.shortcuts import render
from django.http import FileResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from drf_spectacular.utils import extend_schema, extend_schema_view  # 추가된 부분

from .models import SpecDocument
from .serializers import SpecDocumentSerializer
from tasks.services import create_task_assignments_for_spec  # 업무 배분 서비스


@extend_schema_view(
    list=extend_schema(summary="기획서 목록 조회"),
    retrieve=extend_schema(summary="기획서 상세 조회"),
)
class SpecDocumentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    기획서는 회의록 검토 완료 시 자동 생성되므로 ReadOnlyModelViewSet을 사용하고,
    검토완료/다운로드 액션만 추가합니다.
    """
    queryset = SpecDocument.objects.all().order_by('-created_at')
    serializer_class = SpecDocumentSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="기획서 파일 다운로드")
    @action(detail=True, methods=['get'], url_path='download')
    def download(self, request, pk=None):
        """
        기획서 파일 다운로드 API
        """
        spec = self.get_object()
        if not spec.file:
            return Response({"detail": "등록된 기획서 파일이 없습니다."}, status=status.HTTP_404_NOT_FOUND)
        
        return FileResponse(spec.file.open('rb'), as_attachment=True, filename=spec.file.name)

    @extend_schema(summary="기획서 검토 완료 처리")
    @action(detail=True, methods=['post'], url_path='review-complete')
    def review_complete(self, request, pk=None):
        """
        2-1. 기획서 검토완료 버튼 클릭 시 호출
        - 기획서 상태를 REVIEWED로 변경
        - 작업중인 사원을 제외한 업무 배분 API/서비스 연동
        """
        spec = self.get_object()

        if spec.status == SpecDocument.Status.REVIEWED:
            return Response(
                {"detail": "이미 검토 완료된 기획서입니다."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 1. 기획서 상태 변경
        spec.status = SpecDocument.Status.REVIEWED
        spec.save()

        # 2. 업무 배분 자동화 서비스 호출
        result = create_task_assignments_for_spec(spec.id)

        serializer = self.get_serializer(spec)
        return Response(
            {
                "message": "기획서 검토가 완료되었으며, 가능한 사원에게 업무 배정이 생성되었습니다.",
                "assignment_result": result,
                "data": serializer.data
            },
            status=status.HTTP_200_OK
        )
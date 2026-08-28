#meetings/views.py
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiTypes,
    OpenApiResponse,
)

from meetings.models import MeetingNote, SpecDocument
from meetings.serializers import (
    MeetingNoteSerializer,
    MeetingNoteCreateSerializer,
    SpecDocumentSerializer,
)
from projects.models import PipelineHistory, Project


@extend_schema_view(
    get=extend_schema(
        tags=['1단계 - 회의록 & 기획서'],
        summary='회의록 목록 조회',
        description='등록된 전체 회의록 및 관련 기획서(spec_documents) 목록을 조회합니다.',
        responses={200: MeetingNoteSerializer(many=True)}
    ),
    post=extend_schema(
        tags=['1단계 - 회의록 & 기획서'],
        summary='신규 회의록 등록',
        description='새로운 회의록을 작성합니다. 작성자(`created_by`)는 요청을 보낸 유저로 자동 매핑됩니다.',
        request=MeetingNoteCreateSerializer,
        responses={201: MeetingNoteCreateSerializer}
    )
)
class MeetingNoteListCreateView(generics.ListCreateAPIView):
    """
    회의록 목록 조회 및 신규 작성 API
    GET /api/meetings/notes/
    POST /api/meetings/notes/
    """
    queryset = MeetingNote.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return MeetingNoteCreateSerializer
        return MeetingNoteSerializer

    def perform_create(self, serializer):
        # 작성자를 현재 로그인 유저로 지정
        serializer.save(created_by=self.request.user)


@extend_schema_view(
    get=extend_schema(
        tags=['1단계 - 회의록 & 기획서'],
        summary='회의록 상세 조회',
        description='특정 회의록의 상세 내용을 조회합니다.',
        responses={200: MeetingNoteSerializer}
    ),
    put=extend_schema(
        tags=['1단계 - 회의록 & 기획서'],
        summary='회의록 전체 수정',
        description='회의록 전체 필드를 수정합니다.',
        responses={200: MeetingNoteSerializer}
    ),
    patch=extend_schema(
        tags=['1단계 - 회의록 & 기획서'],
        summary='회의록 부분 수정',
        description='회의록 필드 일부를 수정합니다.',
        responses={200: MeetingNoteSerializer}
    ),
    delete=extend_schema(
        tags=['1단계 - 회의록 & 기획서'],
        summary='회의록 삭제',
        description='특정 회의록을 삭제합니다.',
        responses={204: None}
    )
)
class MeetingNoteDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    회의록 상세 조회 / 수정 / 삭제 API
    GET/PUT/PATCH/DELETE /api/meetings/notes/{id}/
    """
    queryset = MeetingNote.objects.all()
    serializer_class = MeetingNoteSerializer
    permission_classes = [permissions.IsAuthenticated]


class MeetingNoteAnalyzeView(APIView):
    """
    회의록 AI 핵심 요약 및 기획 초안 자동 생성 API
    POST /api/meetings/notes/{id}/analyze/
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['1단계 - 회의록 & 기획서'],
        summary='회의록 AI 분석 및 기획 초안 생성',
        description='회의록 텍스트를 AI로 분석하여 핵심 요약(`summary_content`)을 등록하고 기획서(`SpecDocument`) 초안을 자동 생성합니다.',
        parameters=[
            OpenApiParameter(
                name='pk',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description='분석할 회의록 ID'
            )
        ],
        responses={
            200: OpenApiResponse(
                description='AI 분석 및 기획서 생성 완료',
                response=MeetingNoteSerializer
            ),
            404: OpenApiResponse(description='존재하지 않는 회의록')
        }
    )
    def post(self, request, pk):
        meeting = get_object_or_404(MeetingNote, pk=pk)

        # AI 요약 수행 상태 업데이트
        meeting.status = MeetingNote.Status.PROCESSING
        meeting.save()

        # -------------------------------------------------------------
        # [AI 처리 로직 모킹/연동 영역]
        # 실제 LLM API 호출(ex: OpenAI / Gemini API) 결과를 적용합니다.
        # -------------------------------------------------------------
        ai_summary = f"[{meeting.title}]에 대한 핵심 요약: 주요 요구사항 정리 및 시스템 아키텍처 수립 필요."
        
        meeting.summary_content = ai_summary
        meeting.status = MeetingNote.Status.REVIEWED
        meeting.save()

        # 분석된 회의록 기반으로 SpecDocument(기획서) 초안 자동 생성
        spec = SpecDocument.objects.create(
            meeting=meeting,
            title=f"{meeting.title} - 기획 초안",
            overview=f"회의록 '{meeting.title}'을 기반으로 자동 생성된 기획서입니다.",
            background="고객사 요구사항 반영 및 서비스 고도화",
            target_scope="주요 백엔드 API 구현 및 프론트엔드 파이프라인 연동",
            key_features="1. 회의록 AI 분석\n2. 기획서 검토 및 승인\n3. 요구사항 및 업무 배정 자동화"
        )

        return Response({
            "message": "회의록 AI 분석 및 기획서 초안 생성이 완료되었습니다.",
            "meeting": MeetingNoteSerializer(meeting).data,
            "created_spec": SpecDocumentSerializer(spec).data
        }, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
        tags=['1단계 - 회의록 & 기획서'],
        summary='기획서 목록 조회',
        description='생성된 기획서(SpecDocument) 목록을 조회합니다.',
        responses={200: SpecDocumentSerializer(many=True)}
    ),
    post=extend_schema(
        tags=['1단계 - 회의록 & 기획서'],
        summary='기획서 직접 작성',
        description='신규 기획서를 수동으로 작성합니다.',
        responses={201: SpecDocumentSerializer}
    )
)
class SpecDocumentListCreateView(generics.ListCreateAPIView):
    """
    기획서 목록 조회 및 신규 생성 API
    GET /api/meetings/specs/
    POST /api/meetings/specs/
    """
    queryset = SpecDocument.objects.all()
    serializer_class = SpecDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]


@extend_schema_view(
    get=extend_schema(
        tags=['1단계 - 회의록 & 기획서'],
        summary='기획서 상세 조회',
        description='특정 기획서의 상세 정보를 조회합니다.',
        responses={200: SpecDocumentSerializer}
    ),
    put=extend_schema(
        tags=['1단계 - 회의록 & 기획서'],
        summary='기획서 전체 수정',
        description='기획서 내용을 전체 수정합니다.',
        responses={200: SpecDocumentSerializer}
    ),
    patch=extend_schema(
        tags=['1단계 - 회의록 & 기획서'],
        summary='기획서 부분 수정',
        description='기획서 내용 일부를 수정합니다.',
        responses={200: SpecDocumentSerializer}
    )
)
class SpecDocumentDetailView(generics.RetrieveUpdateAPIView):
    """
    기획서 상세 조회 및 수정 API
    GET/PUT/PATCH /api/meetings/specs/{id}/
    """
    queryset = SpecDocument.objects.all()
    serializer_class = SpecDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]


class SpecDocumentReviewView(APIView):
    """
    기획서 검토 승인 및 히스토리 자동 기록 API
    PATCH /api/meetings/specs/{id}/review/
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['1단계 - 회의록 & 기획서'],
        summary='기획서 검토 및 승인 처리',
        description='기획서에 대한 검토 의견(`review_comment`)과 검토자 정보를 업데이트합니다. `project_id` 전달 시 `PipelineHistory` 타임라인 이력이 자동 생성됩니다.',
        parameters=[
            OpenApiParameter(
                name='pk',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description='검토 승인할 기획서 ID'
            )
        ],
        responses={
            200: OpenApiResponse(
                description='기획서 검토 완료 및 히스토리 기록 완료',
                response=SpecDocumentSerializer
            )
        }
    )
    def patch(self, request, pk):
        spec = get_object_or_404(SpecDocument, pk=pk)
        review_comment = request.data.get('review_comment', '')
        project_id = request.data.get('project_id', None)

        # 검토자 지정 및 의견 업데이트
        spec.reviewer = request.user
        spec.review_comment = review_comment
        spec.save()

        # 프로젝트 ID가 넘어온 경우 PipelineHistory 타임라인 로그 자동 생성
        if project_id:
            project = get_object_or_404(Project, pk=project_id)
            PipelineHistory.objects.create(
                project=project,
                meeting=spec.meeting,
                spec=spec,
                step_type='SPEC_GENERATED',
                title=f"기획서 검토 완료: {spec.title}",
                description=f"검토자: {request.user.username} / 의견: {review_comment}",
                actor=request.user
            )

        return Response({
            "message": "기획서 검토가 완료되었습니다.",
            "spec": SpecDocumentSerializer(spec).data
        }, status=status.HTTP_200_OK)
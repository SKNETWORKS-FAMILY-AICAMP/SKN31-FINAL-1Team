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
from common.models import CommonCode
from users.permissions import IsAdminUserOnly


def _proposal_status(code_id: str):
    # CommonCode.code_id는 테이블 전체에서 전역 유일해서(그룹별로 스코프되지 않음)
    # REQSPEC_STATUS와 안 겹치도록 PROPOSAL_ 접두사를 붙여 시드했다(migrations/0005 참고).
    return CommonCode.objects.filter(group_id='PROPOSAL_STATUS', code_id=f'PROPOSAL_{code_id}').first()


def _log_pipeline_history(spec, step_type, title, description, actor):
    # PipelineHistory.project는 필수 필드라, 소속 프로젝트가 없는(레거시/테스트) 회의록이면
    # 이력을 남길 방법이 없다 — 그런 경우는 조용히 건너뛴다(이력 누락이 500 에러보다 낫다).
    project = spec.meeting.project if spec.meeting else None
    if not project:
        return
    PipelineHistory.objects.create(
        project=project, meeting=spec.meeting, spec=spec,
        step_type=step_type, title=title, description=description, actor=actor,
    )


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

    def get_queryset(self):
        queryset = super().get_queryset()
        project_id = self.request.query_params.get('project', None)
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return queryset

    def perform_create(self, serializer):
        # 작성자를 현재 로그인 유저로 지정
        serializer.save(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        # MeetingNoteCreateSerializer는 write용이라 응답에 id가 없다 — 생성 직후 프론트가
        # "방금 만든 회의록"을 곧바로 선택/이동하려면 id가 필요하므로(NewDocumentModal과 동일한
        # 패턴) 응답만 MeetingNoteSerializer 모양으로 바꿔 돌려준다.
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(MeetingNoteSerializer(serializer.instance).data, status=status.HTTP_201_CREATED, headers=headers)


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

        # 분석된 회의록 기반으로 SpecDocument(기획서) 초안 자동 생성 — 7개 섹션 전부 채운다.
        # 실제 LLM 연동 전까지는 회의록 원문을 섹션별로 요약하는 자리표시(placeholder) 문구.
        spec = SpecDocument.objects.create(
            meeting=meeting,
            title=f"{meeting.title} - 기획 초안",
            overview=f"회의록 '{meeting.title}'을 기반으로 자동 생성된 기획서입니다.",
            problem_definition="[AI 생성 예정] 회의록에서 언급된 문제 정의를 정리합니다.",
            target_users="[AI 생성 예정] 회의록에서 언급된 대상 사용자를 정리합니다.",
            key_features="1. 회의록 AI 분석\n2. 기획서 검토 및 승인\n3. 요구사항 및 업무 배정 자동화",
            user_scenarios="[AI 생성 예정] 회의록 내용을 바탕으로 한 사용자 시나리오를 정리합니다.",
            tech_stack="[AI 생성 예정] 회의록에서 언급된 기술 스택 및 제약사항을 정리합니다.",
            final_decisions="[AI 생성 예정] 회의록의 최종 결정 사항을 정리합니다.",
            status_code=_proposal_status('DRAFT'),
        )
        _log_pipeline_history(
            spec, 'SPEC_GENERATED', f"기획서 초안 생성: {spec.title}",
            f"회의록 '{meeting.title}' 기반 AI 자동 생성", request.user,
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
    GET /api/meetings/specs/?meeting={meeting_id}
    POST /api/meetings/specs/
    """
    queryset = SpecDocument.objects.all()
    serializer_class = SpecDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        meeting_id = self.request.query_params.get('meeting', None)
        if meeting_id:
            queryset = queryset.filter(meeting_id=meeting_id)
        return queryset


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


class SpecDocumentSubmitReviewView(APIView):
    """
    기획서 검토 요청 API (작성자 전용)
    PATCH /api/meetings/specs/{id}/submit-review/
    작성자가 초안(DRAFT) 또는 반려(REJECTED) 상태의 기획서를 검토대기(PENDING_REVIEW)로 전환한다.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['1단계 - 회의록 & 기획서'],
        summary='기획서 검토 요청 (작성자 전용)',
        description='기획서를 검토대기(PENDING_REVIEW) 상태로 전환합니다. 이 회의록을 작성한 본인만 요청할 수 있습니다.',
        responses={200: SpecDocumentSerializer, 403: OpenApiTypes.OBJECT}
    )
    def patch(self, request, pk):
        spec = get_object_or_404(SpecDocument, pk=pk)
        if spec.meeting.created_by_id != request.user.id:
            return Response({"error": "이 회의록의 작성자만 검토를 요청할 수 있습니다."}, status=status.HTTP_403_FORBIDDEN)
        spec.status_code = _proposal_status('PENDING_REVIEW')
        spec.review_comment = None
        spec.save()
        return Response(SpecDocumentSerializer(spec).data, status=status.HTTP_200_OK)


class SpecDocumentApproveView(APIView):
    """
    기획서 승인 API (PM 전용)
    POST /api/meetings/specs/{id}/approve/
    """
    permission_classes = [IsAdminUserOnly]

    @extend_schema(
        tags=['1단계 - 회의록 & 기획서'],
        summary='기획서 승인 (PM 전용)',
        description='기획서를 승인(APPROVED) 상태로 전환하고 PipelineHistory에 이력을 남깁니다.',
        responses={200: SpecDocumentSerializer}
    )
    def post(self, request, pk):
        spec = get_object_or_404(SpecDocument, pk=pk)
        spec.status_code = _proposal_status('APPROVED')
        spec.reviewer = request.user
        spec.review_comment = None
        spec.save()
        _log_pipeline_history(
            spec, 'SPEC_GENERATED', f"기획서 승인: {spec.title}",
            f"승인자: {request.user.username}", request.user,
        )
        return Response(SpecDocumentSerializer(spec).data, status=status.HTTP_200_OK)


class SpecDocumentRejectView(APIView):
    """
    기획서 반려 API (PM 전용)
    POST /api/meetings/specs/{id}/reject/
    """
    permission_classes = [IsAdminUserOnly]

    @extend_schema(
        tags=['1단계 - 회의록 & 기획서'],
        summary='기획서 반려 (PM 전용)',
        description='기획서를 반려(REJECTED) 상태로 전환합니다. 반려 사유(`reason`)는 필수입니다.',
        responses={200: SpecDocumentSerializer, 400: OpenApiTypes.OBJECT}
    )
    def post(self, request, pk):
        reason = request.data.get('reason', '').strip()
        if not reason:
            return Response({"error": "반려 사유를 입력해주세요."}, status=status.HTTP_400_BAD_REQUEST)
        spec = get_object_or_404(SpecDocument, pk=pk)
        spec.status_code = _proposal_status('REJECTED')
        spec.reviewer = request.user
        spec.review_comment = reason
        spec.save()
        _log_pipeline_history(
            spec, 'SPEC_GENERATED', f"기획서 반려: {spec.title}",
            f"반려자: {request.user.username} / 사유: {reason}", request.user,
        )
        return Response(SpecDocumentSerializer(spec).data, status=status.HTTP_200_OK)
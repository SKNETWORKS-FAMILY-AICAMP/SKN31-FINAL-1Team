from rest_framework import generics, permissions
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes

from projects.models import Project, PipelineHistory
from projects.serializers import ProjectSerializer, PipelineHistorySerializer


@extend_schema_view(
    get=extend_schema(
        tags=['0단계 - 프로젝트 관리'],
        summary='프로젝트 목록 조회',
        description='등록된 전체 프로젝트 목록을 조회합니다.',
        responses={200: ProjectSerializer(many=True)}
    ),
    post=extend_schema(
        tags=['0단계 - 프로젝트 관리'],
        summary='신규 프로젝트 생성',
        description='새로운 프로젝트를 생성합니다. 작성자(`owner`)는 요청을 보낸 유저로 자동 지정됩니다.',
        responses={201: ProjectSerializer}
    )
)
class ProjectListCreateView(generics.ListCreateAPIView):
    """
    프로젝트 목록 조회 및 신규 생성 API
    GET/POST /api/projects/
    """
    # 정렬 없이 반환하면 DB가 보통 PK(=가장 먼저 만든 프로젝트) 순서로 돌려준다.
    # 프론트 여러 화면(history/tasks/documents)이 "단일 프로젝트 운영" 전제로
    # projects[0]을 "현재 프로젝트"로 그대로 쓰는데, 테스트 중 새 프로젝트가
    # 계속 생겨나면서 projects[0]이 09-01에 만든 옛날 프로젝트에 고정돼버려
    # 최근 작업(새 프로젝트) 이력이 화면에 전혀 안 보이는 문제가 있었다.
    # 최신순으로 내려줘서 projects[0]이 "가장 최근에 만든 프로젝트"가 되게 한다.
    queryset = Project.objects.all().order_by('-created_at')
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


@extend_schema_view(
    get=extend_schema(
        tags=['0단계 - 프로젝트 관리'],
        summary='프로젝트 상세 조회',
        description='특정 프로젝트의 상세 정보를 조회합니다.',
        responses={200: ProjectSerializer}
    ),
    put=extend_schema(
        tags=['0단계 - 프로젝트 관리'],
        summary='프로젝트 전체 수정',
        description='특정 프로젝트의 정보를 전체 수정합니다.',
        responses={200: ProjectSerializer}
    ),
    patch=extend_schema(
        tags=['0단계 - 프로젝트 관리'],
        summary='프로젝트 부분 수정',
        description='특정 프로젝트의 정보 일부를 수정합니다.',
        responses={200: ProjectSerializer}
    ),
    delete=extend_schema(
        tags=['0단계 - 프로젝트 관리'],
        summary='프로젝트 삭제',
        description='특정 프로젝트를 삭제합니다.',
        responses={204: None}
    )
)
class ProjectDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    프로젝트 상세 조회 / 수정 / 삭제 API
    GET/PUT/PATCH/DELETE /api/projects/{id}/
    """
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]


@extend_schema(
    tags=['4단계 - 파이프라인 이력'],
    summary='프로젝트 파이프라인 타임라인 이력 조회',
    description='특정 프로젝트의 전체 파이프라인 흐름(회의록 → 기획서 → 요구사항 → 업무 배정) 이력 로그를 시간순으로 조회합니다. 프론트엔드의 `/history` 타임라인 페이지에서 사용됩니다.',
    parameters=[
        OpenApiParameter(
            name='project_id',
            type=OpenApiTypes.INT,
            location=OpenApiParameter.PATH,
            description='타임라인 이력을 조회할 프로젝트 ID'
        )
    ],
    responses={200: PipelineHistorySerializer(many=True)}
)
class PipelineHistoryListView(generics.ListAPIView):
    """
    /history 페이지 타임라인 전체 이력 조회 API
    GET /api/projects/{id}/history/
    """
    serializer_class = PipelineHistorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        project_id = self.kwargs.get('project_id')
        return PipelineHistory.objects.filter(project_id=project_id).select_related(
            'project', 'actor', 'meeting', 'spec', 'requirement', 'task'
        )
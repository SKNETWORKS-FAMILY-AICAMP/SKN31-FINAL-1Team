#requirements/views.py
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

from requirements.models import RequirementDefinition, RequirementItem
from requirements.serializers import (
    RequirementDefinitionSerializer,
    RequirementDefinitionCreateSerializer,
    RequirementItemSerializer,
)
from meetings.models import SpecDocument


@extend_schema_view(
    get=extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='요구사항 정의서 목록 조회',
        description='등록된 전체 요구사항 정의서 목록과 포함된 세부 항목들을 함께 조회합니다.',
        responses={200: RequirementDefinitionSerializer(many=True)}
    ),
    post=extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='요구사항 정의서 신규 등록',
        description='새로운 요구사항 정의서를 생성합니다. 작성자(`created_by`)는 현재 로그인한 유저로 자동 지정됩니다.',
        request=RequirementDefinitionCreateSerializer,
        responses={201: RequirementDefinitionCreateSerializer}
    )
)
class RequirementDefinitionListCreateView(generics.ListCreateAPIView):
    """
    요구사항 정의서 목록 조회 및 신규 작성 API
    GET /api/requirements/
    POST /api/requirements/
    """
    queryset = RequirementDefinition.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return RequirementDefinitionCreateSerializer
        return RequirementDefinitionSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


@extend_schema_view(
    get=extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='요구사항 정의서 상세 조회',
        description='특정 요구사항 정의서의 상세 정보 및 하위 요구사항 항목들을 조회합니다.',
        responses={200: RequirementDefinitionSerializer}
    ),
    put=extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='요구사항 정의서 전체 수정',
        description='특정 요구사항 정의서의 전체 필드를 수정합니다.',
        responses={200: RequirementDefinitionSerializer}
    ),
    patch=extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='요구사항 정의서 부분 수정',
        description='특정 요구사항 정의서의 일부 필드를 수정합니다.',
        responses={200: RequirementDefinitionSerializer}
    ),
    delete=extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='요구사항 정의서 삭제',
        description='특정 요구사항 정의서를 삭제합니다.',
        responses={204: None}
    )
)
class RequirementDefinitionDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    요구사항 정의서 상세 조회 / 수정 / 삭제 API
    GET/PUT/PATCH/DELETE /api/requirements/{id}/
    """
    queryset = RequirementDefinition.objects.all()
    serializer_class = RequirementDefinitionSerializer
    permission_classes = [permissions.IsAuthenticated]


class RequirementExtractView(APIView):
    """
    기획서(SpecDocument) 기반 AI 요구사항 항목 자동 추출 API
    POST /api/requirements/{id}/extract/
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='기획서 기반 AI 세부 요구사항 추출',
        description='연관된 기획서(`SpecDocument`)의 내용을 분석하여 REQ 코드별 세부 요구사항 항목(`RequirementItem`)을 자동 생성 및 바인딩합니다.',
        parameters=[
            OpenApiParameter(
                name='pk',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description='요구사항 추출을 실행할 요구사항 정의서 ID'
            )
        ],
        responses={
            201: OpenApiResponse(
                description='AI 요구사항 항목 추출 완료',
                response=RequirementItemSerializer(many=True)
            ),
            404: OpenApiResponse(description='존재하지 않는 요구사항 정의서')
        }
    )
    def post(self, request, pk):
        req_def = get_object_or_404(RequirementDefinition, pk=pk)
        spec = req_def.spec

        # -------------------------------------------------------------
        # [AI 요구사항 추출 로직 모킹/연동 영역]
        # 기획서(spec) 텍스트를 파싱하여 REQ 코드별 항목 자동 작성
        # -------------------------------------------------------------
        extracted_items = [
            {
                "req_code": "REQ-01",
                "req_name": "사용자 인증 및 권한 관리",
                "description": f"기획서 '{spec.title}' 기준: AbstractUser 확장 기반 JWT API 구현",
                "difficulty": "중",
                "category": "보안/인증"
            },
            {
                "req_code": "REQ-02",
                "req_name": "파이프라인 이력 자동 로깅",
                "description": "기획서 검토 및 업무 배정 시 PipelineHistory 테이블 기록",
                "difficulty": "하",
                "category": "데이터베이스"
            }
        ]

        created_objs = []
        for item in extracted_items:
            obj = RequirementItem.objects.create(
                req_def=req_def,
                req_code=item["req_code"],
                req_name=item["req_name"],
                description=item["description"],
                difficulty=item["difficulty"],
                category=item["category"]
            )
            created_objs.append(obj)

        return Response({
            "message": f"기획서 기반으로 {len(created_objs)}개의 요구사항 항목이 성공적으로 추출되었습니다.",
            "extracted_items": RequirementItemSerializer(created_objs, many=True).data
        }, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='세부 요구사항 항목 목록 조회',
        description='등록된 전체 세부 요구사항 항목(`RequirementItem`) 목록을 조회합니다.',
        responses={200: RequirementItemSerializer(many=True)}
    ),
    post=extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='세부 요구사항 항목 직접 추가',
        description='특정 요구사항 정의서 하위에 세부 항목을 수동으로 추가합니다.',
        responses={201: RequirementItemSerializer}
    )
)
class RequirementItemViewSet(generics.ListCreateAPIView):
    """
    요구사항 세부 항목(RequirementItem) CRUD API
    GET/POST /api/requirements/items/
    """
    queryset = RequirementItem.objects.all()
    serializer_class = RequirementItemSerializer
    permission_classes = [permissions.IsAuthenticated]
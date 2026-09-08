import logging
from django.db import transaction
from django.shortcuts import get_object_or_404
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

from requirements.models import RequirementDefinition, RequirementItem
from requirements.serializers import (
    RequirementDefinitionSerializer,
    RequirementDefinitionCreateSerializer,
    RequirementItemSerializer,
)
from meetings.models import SpecDocument
from common.models import CommonCode

# AI 에이전트 및 Pydantic 스키마 임포트
from requirement_draft.agent import generate_requirements
from requirement_draft.schemas import PlanDocument

logger = logging.getLogger(__name__)


@extend_schema_view(
    get=extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='요구사항 정의서 목록 조회',
        description='등록된 전체 요구사항 정의서 목록을 조회합니다. `spec` 또는 `project` ID 쿼리 파라미터를 이용해 특정 기획서/프로젝트별 필터링이 가능합니다.',
        parameters=[
            OpenApiParameter(
                name='spec',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='기획서 ID (SpecDocument ID)로 필터링',
                required=False
            ),
            OpenApiParameter(
                name='project',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='프로젝트 ID (Project ID)로 필터링',
                required=False
            ),
        ],
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
    GET /api/requirements/?spec=1
    GET /api/requirements/?project=2
    POST /api/requirements/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return RequirementDefinitionCreateSerializer
        return RequirementDefinitionSerializer

    def get_queryset(self):
        queryset = RequirementDefinition.objects.all().select_related('spec', 'project', 'status_code', 'created_by')
        
        # 쿼리 파라미터 필터링
        spec_id = self.request.query_params.get('spec')
        project_id = self.request.query_params.get('project')

        if spec_id:
            queryset = queryset.filter(spec_id=spec_id)
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        return queryset

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
    queryset = RequirementDefinition.objects.all().select_related(
        'spec', 'project', 'status_code', 'created_by'
    ).prefetch_related('items__priority_code')
    serializer_class = RequirementDefinitionSerializer
    permission_classes = [permissions.IsAuthenticated]


class RequirementExtractView(APIView):
    """
    POST /api/requirements/{spec_id}/extract/
    기획서(SpecDocument) 데이터를 AI 에이전트로 분석하여 요구사항 정의서 및 세부 항목(RequirementItem)을 생성합니다.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='기획서 기반 AI 요구사항 자동 추출',
        description='특정 기획서(SpecDocument) 원문을 AI 에이전트가 분석하여 요구사항 정의서와 세부 항목(RequirementItem)들을 생성합니다.',
        responses={
            201: RequirementDefinitionSerializer,
            400: OpenApiResponse(description="잘못된 기획서 데이터 구조"),
            500: OpenApiResponse(description="AI 연동 또는 DB 저장 오류")
        }
    )
    def post(self, request, spec_id):
        # 1. 대상 기획서 조회
        spec_document = get_object_or_404(SpecDocument, spec_id=spec_id)

        # 2. SpecDocument DB 객체 -> PlanDocument Pydantic 스키마 변환 데이터 구성
        # 2-1) goal (단수형 문자열 필수) 변환
        raw_goals = getattr(spec_document, "goals", [])
        if isinstance(raw_goals, list):
            goal_str = "\n".join([str(g) for g in raw_goals if g]) if raw_goals else getattr(spec_document, "overview", "요구사항 분석 및 기획서 도출")
        else:
            goal_str = str(raw_goals) if raw_goals else "요구사항 분석 및 기획서 도출"

        # 2-2) requirements (최소 1개 이상 항목 리스트 필수) 구성
        raw_features = getattr(spec_document, "key_features", [])
        if raw_features and isinstance(raw_features, list):
            requirements_input = [
                {
                    "id": f"REQ-{i+1:02d}",
                    "title": str(feat),
                    "description": str(feat)
                }
                for i, feat in enumerate(raw_features)
            ]
        else:
            requirements_input = [
                {
                    "id": "REQ-01",
                    "title": getattr(spec_document, "title", "기본 요구사항"),
                    "description": getattr(spec_document, "overview", "기획서 기반 기본 기능 요구사항")
                }
            ]

        plan_dict = {
            "project_id": str(spec_document.project.id) if hasattr(spec_document, "project") and spec_document.project else "DEFAULT_PROJECT",
            "title": getattr(spec_document, "title", "기획서 초안"),
            "overview": getattr(spec_document, "overview", ""),
            "background": getattr(spec_document, "background", ""),
            "goal": goal_str,
            "target_users": getattr(spec_document, "target_users", []),
            "key_features": getattr(spec_document, "key_features", []),
            "tech_constraints": getattr(spec_document, "tech_constraints", []),
            "requirements": requirements_input,
        }

        # 3. PlanDocument 스키마 검증
        try:
            plan_input = PlanDocument.model_validate(plan_dict)
        except Exception as e:
            logger.error(f"PlanDocument 변환 실패 (spec_id: {spec_id}): {e}")
            return Response(
                {
                    "error": "INVALID_SPEC_STRUCTURE",
                    "details": f"기획서 데이터를 AI 입력 규격으로 변환할 수 없습니다: {str(e)}"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # 4. AI 에이전트 실행 (generate_requirements)
        try:
            ai_output = generate_requirements(
                plan=plan_input,
                plan_id=str(spec_document.spec_id)
            )
        except Exception as e:
            logger.exception(f"AI 요구사항 추출 실패 (spec_id: {spec_id}): {e}")
            return Response(
                {
                    "error": "AI_GENERATION_FAILED",
                    "details": f"AI 요구사항 추출 중 오류가 발생했습니다: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # 5. DB 저장 및 기존 요구사항 정의서 연동 (트랜잭션)
        try:
            with transaction.atomic():
                # 초기 승인 상태(PENDING_REVIEW / 검토대기) 공통 코드 조회
                pending_status = CommonCode.objects.filter(
                    group_id='REQSPEC_STATUS',
                    code_id__in=['PENDING_REVIEW', 'PENDING', 'REQSPEC_STATUS_PENDING']
                ).first()

                # 기획서와 1:1 대응되는 RequirementDefinition 생성 또는 조회
                req_def, created = RequirementDefinition.objects.get_or_create(
                    spec=spec_document,
                    defaults={
                        'project': spec_document.project if hasattr(spec_document, "project") else None,
                        'title': f"{spec_document.title} - 요구사항 정의서",
                        'status_code': pending_status,
                        'created_by': request.user
                    }
                )

                # 재추출 시 상태를 다시 PENDING_REVIEW로 초기화
                if not created and pending_status:
                    req_def.status_code = pending_status
                    req_def.save()

                # 기존 생성 항목 초기화 (재추출 시 중복 방지)
                RequirementItem.objects.filter(req_def=req_def).delete()

                # 공통코드 쿼리 횟수를 줄이기 위한 캐싱
                priority_codes = {
                    c.code_id: c for c in CommonCode.objects.filter(group_id='REQ_PRIORITY')
                }

                # AI 추출 결과를 RequirementItem 모델 객체 생성
                items_to_create = []
                for index, req_item in enumerate(ai_output.requirements, start=1):
                    # priority 파싱 (Enum 또는 문자열 안전 처리)
                    raw_priority = getattr(req_item, "priority", "MEDIUM")
                    priority_str = getattr(raw_priority, "value", raw_priority)
                    priority_str = str(priority_str).upper() if priority_str else "MEDIUM"

                    # 캐시된 공통 코드에서 우선순위 객체 매핑
                    priority_code_obj = (
                        priority_codes.get(priority_str) or 
                        priority_codes.get(f"REQ_PRIORITY_{priority_str}")
                    )

                    items_to_create.append(
                        RequirementItem(
                            req_def=req_def,
                            req_code=getattr(req_item, "id", f"REQ-{index:02d}"),
                            req_name=getattr(req_item, "title", f"요구사항 {index}"),
                            description=getattr(req_item, "description", ""),
                            priority_code=priority_code_obj,
                            difficulty=getattr(req_item, "difficulty", "중"),
                            category=getattr(req_item, "category_1", getattr(req_item, "category", "기타")),
                            category_2=getattr(req_item, "category_2", None),
                        )
                    )

                # bulk_create를 사용해 한 번의 DB INSERT 쿼리로 배치 저장
                RequirementItem.objects.bulk_create(items_to_create)

            # 6. 생성된 RequirementDefinition 결과를 Serializer로 반환
            serializer = RequirementDefinitionSerializer(req_def)
            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            logger.exception(f"DB 저장 중 오류 발생 (spec_id: {spec_id}): {e}")
            return Response(
                {
                    "error": "DB_SAVE_FAILED",
                    "details": f"추출된 요구사항 DB 저장 실패: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


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
    queryset = RequirementItem.objects.all().select_related('priority_code', 'req_def')
    serializer_class = RequirementItemSerializer
    permission_classes = [permissions.IsAuthenticated]
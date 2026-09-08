# requirements/views.py
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


def process_ai_requirement_extraction(spec_document, user):
    """
    SpecDocument 기반으로 AI 에이전트를 실행하고 
    RequirementDefinition 및 하위 RequirementItem들을 생성/저장하는 공통 헬퍼 함수
    """
    spec_id = spec_document.spec_id

    # 1. SpecDocument DB 객체 -> PlanDocument Pydantic 스키마 변환 데이터 구성
    raw_goals = getattr(spec_document, "goals", [])
    if isinstance(raw_goals, list):
        goal_str = "\n".join([str(g) for g in raw_goals if g]) if raw_goals else getattr(spec_document, "overview", "요구사항 분석 및 기획서 도출")
    else:
        goal_str = str(raw_goals) if raw_goals else "요구사항 분석 및 기획서 도출"

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
        "project_id": str(spec_document.project.id) if getattr(spec_document, "project", None) else "DEFAULT_PROJECT",
        "title": getattr(spec_document, "title", None) or "기획서 초안",
        "overview": getattr(spec_document, "overview", None) or "",
        "background": getattr(spec_document, "background", None) or "",
        "goal": goal_str,
        "target_users": getattr(spec_document, "target_users", None) or [],
        "key_features": getattr(spec_document, "key_features", None) or [],
        "tech_stack": getattr(spec_document, "tech_stack", None) or [],
        "requirements": requirements_input,
        "final_decisions": getattr(spec_document, "final_decisions", None) or [],
        "problem_definition": getattr(spec_document, "problem_definition", None) or "",
        "user_scenarios": getattr(spec_document, "user_scenarios", None) or [],
    }

    # 2. PlanDocument 스키마 검증
    try:
        plan_input = PlanDocument.model_validate(plan_dict)
    except Exception as e:
        logger.error(f"PlanDocument 변환 실패 (spec_id: {spec_id}): {e}")
        raise ValueError(f"기획서 데이터를 AI 입력 규격으로 변환할 수 없습니다: {str(e)}")

    # 3. AI 에이전트 실행 (generate_requirements)
    try:
        ai_output = generate_requirements(
            plan=plan_input,
            plan_id=str(spec_document.spec_id)
        )
    except Exception as e:
        logger.exception(f"AI 요구사항 추출 실패 (spec_id: {spec_id}): {e}")
        raise RuntimeError(f"AI 요구사항 추출 중 오류가 발생했습니다: {str(e)}")

    # 4. DB 저장 및 기존 요구사항 정의서 연동 (트랜잭션)
    with transaction.atomic():
        pending_status = CommonCode.objects.filter(
            group_id='REQSPEC_STATUS',
            code_id__in=['PENDING_REVIEW', 'PENDING', 'REQSPEC_STATUS_PENDING']
        ).first()

        req_def, created = RequirementDefinition.objects.get_or_create(
            spec=spec_document,
            defaults={
                'project': spec_document.project if hasattr(spec_document, "project") else None,
                'title': f"{spec_document.title} - 요구사항 정의서",
                'status_code': pending_status,
                'created_by': user
            }
        )

        if not created and pending_status:
            req_def.status_code = pending_status
            req_def.save()

        # 기존 생성 항목 초기화 (재추출 시 중복 방지)
        RequirementItem.objects.filter(req_def=req_def).delete()

        priority_codes = {
            c.code_id: c for c in CommonCode.objects.filter(group_id='REQ_PRIORITY')
        }

        items_to_create = []
        for index, req_item in enumerate(ai_output.requirements, start=1):
            raw_priority = getattr(req_item, "priority", "MEDIUM")
            priority_str = getattr(raw_priority, "value", raw_priority)
            priority_str = str(priority_str).upper() if priority_str else "MEDIUM"

            priority_code_obj = (
                priority_codes.get(priority_str)
                or priority_codes.get(f"PRIORITY_{priority_str}")
                or priority_codes.get(f"REQ_PRIORITY_{priority_str}")
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

        RequirementItem.objects.bulk_create(items_to_create)

    return req_def


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
        summary='요구사항 정의서 생성 (AI 세부항목 자동 추출 포함)',
        description='기획서 ID(`spec`)를 전달받아 요구사항 정의서 생성과 동시에 AI 에이전트가 세부 항목(RequirementItem)을 자동 추출 및 저장합니다.',
        request=RequirementDefinitionCreateSerializer,
        responses={
            201: RequirementDefinitionSerializer,
            400: OpenApiResponse(description="잘못된 파라미터 또는 기획서 데이터"),
            500: OpenApiResponse(description="AI 생성 또는 저장 오류")
        }
    )
)
class RequirementDefinitionListCreateView(generics.ListCreateAPIView):
    """
    요구사항 정의서 목록 조회 및 AI 일괄 생성 API
    GET /api/requirements/
    POST /api/requirements/   <- 단 한 번의 호출로 AI 자동 생성까지 일괄 처리
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return RequirementDefinitionCreateSerializer
        return RequirementDefinitionSerializer

    def get_queryset(self):
        queryset = RequirementDefinition.objects.all().select_related('spec', 'project', 'status_code', 'created_by')
        
        spec_id = self.request.query_params.get('spec')
        project_id = self.request.query_params.get('project')

        if spec_id:
            queryset = queryset.filter(spec_id=spec_id)
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        return queryset

    def create(self, request, *args, **kwargs):
        """
        POST 요청 시 Request Body의 'spec' (또는 'spec_id')를 이용해
        요구사항 정의서 생성 + AI 세부 항목 추출을 원스톱으로 처리합니다.
        """
        spec_id = request.data.get('spec') or request.data.get('spec_id')
        
        if not spec_id:
            return Response(
                {"error": "REQUIRED_FIELD_MISSING", "details": "기획서 ID(spec)는 필수입니다."},
                status=status.HTTP_400_BAD_REQUEST
            )

        spec_document = get_object_or_404(SpecDocument, spec_id=spec_id)

        try:
            # 통합 헬퍼 함수 호출 (정의서 생성 + AI 세부항목 추출 및 DB 저장)
            req_def = process_ai_requirement_extraction(spec_document, request.user)
            
            # 생성/수정 완료된 정의서와 세부 항목 결과를 리턴
            serializer = RequirementDefinitionSerializer(req_def)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except ValueError as ve:
            return Response(
                {"error": "INVALID_SPEC_STRUCTURE", "details": str(ve)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {"error": "AI_GENERATION_FAILED", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema_view(
    get=extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='요구사항 정의서 상세 조회',
        description='특정 기획서 ID(`spec_id`)에 연관된 요구사항 정의서의 상세 정보 및 하위 요구사항 항목들을 조회합니다.',
        responses={200: RequirementDefinitionSerializer}
    ),
    put=extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='요구사항 정의서 전체 수정',
        description='특정 기획서 ID(`spec_id`)에 연관된 요구사항 정의서의 전체 필드를 수정합니다.',
        responses={200: RequirementDefinitionSerializer}
    ),
    patch=extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='요구사항 정의서 부분 수정',
        description='특정 기획서 ID(`spec_id`)에 연관된 요구사항 정의서의 일부 필드를 수정합니다.',
        responses={200: RequirementDefinitionSerializer}
    ),
    delete=extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='요구사항 정의서 삭제',
        description='특정 기획서 ID(`spec_id`)에 연관된 요구사항 정의서를 삭제합니다.',
        responses={204: None}
    )
)
class RequirementDefinitionDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = RequirementDefinition.objects.all().select_related(
        'spec', 'project', 'status_code', 'created_by'
    ).prefetch_related('items__priority_code')
    serializer_class = RequirementDefinitionSerializer
    permission_classes = [permissions.IsAuthenticated]

    lookup_field = 'spec_id'
    lookup_url_kwarg = 'spec_id'


class RequirementExtractView(APIView):
    """
    POST /api/requirements/{spec_id}/extract/
    (기존 단독 재추출 API가 필요할 경우 유지)
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='기획서 기반 AI 요구사항 재추출',
        description='특정 기획서(SpecDocument) 원문을 AI 에이전트가 다시 분석하여 세부 항목을 업데이트합니다.',
        responses={201: RequirementDefinitionSerializer}
    )
    def post(self, request, spec_id):
        spec_document = get_object_or_404(SpecDocument, spec_id=spec_id)
        try:
            req_def = process_ai_requirement_extraction(spec_document, request.user)
            serializer = RequirementDefinitionSerializer(req_def)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except ValueError as ve:
            return Response({"error": "INVALID_SPEC_STRUCTURE", "details": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": "AI_GENERATION_FAILED", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema_view(
    get=extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='세부 요구사항 항목 목록 조회',
        responses={200: RequirementItemSerializer(many=True)}
    ),
    post=extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='세부 요구사항 항목 직접 추가',
        responses={201: RequirementItemSerializer}
    )
)
class RequirementItemViewSet(generics.ListCreateAPIView):
    queryset = RequirementItem.objects.all().select_related('priority_code', 'req_def')
    serializer_class = RequirementItemSerializer
    permission_classes = [permissions.IsAuthenticated]


@extend_schema_view(
    get=extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='세부 요구사항 항목 단건 조회',
        responses={200: RequirementItemSerializer}
    ),
    put=extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='세부 요구사항 항목 전체 수정',
        responses={200: RequirementItemSerializer}
    ),
    patch=extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='세부 요구사항 항목 부분 수정',
        responses={200: RequirementItemSerializer}
    ),
    delete=extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='세부 요구사항 항목 삭제',
        responses={204: None}
    )
)
class RequirementItemDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = RequirementItem.objects.all().select_related('priority_code', 'req_def')
    serializer_class = RequirementItemSerializer
    permission_classes = [permissions.IsAuthenticated]
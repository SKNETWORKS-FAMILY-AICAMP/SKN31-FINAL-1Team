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
from users.permissions import IsPMUser, IsOwnerOrPM  # PM 권한 검증
from notifications.services import notify_user, notify_all_pms  # 알림 서비스
from projects.models import PipelineHistory

# AI 에이전트 및 Pydantic 스키마 임포트
from requirement_draft.agent import generate_requirements
from requirement_draft.schemas import PlanDocument

logger = logging.getLogger(__name__)


def get_target_author(req_def):
    """요구사항 정의서 작성자 또는 기획서 작성자를 안전하게 반환하는 헬퍼 함수"""
    if getattr(req_def, 'created_by', None):
        return req_def.created_by
    if hasattr(req_def, 'spec') and getattr(req_def.spec, 'created_by', None):
        return req_def.spec.created_by
    return None


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
        # SpecDocument엔 project 필드가 없다 — meeting을 거쳐야 함(위 defaults의 project 필드와 동일한 이유)
        "project_id": str(spec_document.meeting.project_id) if spec_document.meeting.project_id else "DEFAULT_PROJECT",
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
        draft_status = CommonCode.objects.filter(
            group_id='REQSPEC_STATUS',
            code_id='DRAFT'
        ).first()

        req_def, created = RequirementDefinition.objects.get_or_create(
            spec=spec_document,
            defaults={
                # SpecDocument엔 project 필드가 없다 — meeting을 거쳐야 프로젝트를 알 수 있다
                # (spec_document.project로 잘못 참조하면 hasattr()가 항상 False라 계속 None으로
                # 저장되는 버그가 있었음, 2026-09-08부터 발생).
                'project': spec_document.meeting.project,
                'title': f"{spec_document.title} - 요구사항 정의서",
                'status_code': draft_status,
                'created_by': user
            }
        )

        if not created and draft_status:
            req_def.status_code = draft_status
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
                    order=index,
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
    queryset = RequirementDefinition.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return RequirementDefinitionCreateSerializer
        return RequirementDefinitionSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        req_def_id = self.request.query_params.get('req_def')
        if req_def_id:
            queryset = queryset.filter(req_def_id=req_def_id)
        return queryset

    def create(self, request, *args, **kwargs):
        spec_id = request.data.get('spec') or request.data.get('spec_id')
        
        if not spec_id:
            return Response(
                {"error": "REQUIRED_FIELD_MISSING", "details": "기획서 ID(spec)는 필수입니다."},
                status=status.HTTP_400_BAD_REQUEST
            )

        spec_document = get_object_or_404(SpecDocument, spec_id=spec_id)

        try:
            req_def = process_ai_requirement_extraction(spec_document, request.user)
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
        parameters=[
            OpenApiParameter(name='spec_id', type=OpenApiTypes.INT, location=OpenApiParameter.PATH, description='조회할 기획서 ID')
        ],
        responses={200: RequirementDefinitionSerializer}
    ),
    put=extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='요구사항 정의서 전체 수정',
        parameters=[
            OpenApiParameter(name='spec_id', type=OpenApiTypes.INT, location=OpenApiParameter.PATH, description='수정할 기획서 ID')
        ],
        responses={200: RequirementDefinitionSerializer}
    ),
    patch=extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='요구사항 정의서 부분 수정',
        parameters=[
            OpenApiParameter(name='spec_id', type=OpenApiTypes.INT, location=OpenApiParameter.PATH, description='수정할 기획서 ID')
        ],
        responses={200: RequirementDefinitionSerializer}
    ),
    delete=extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='요구사항 정의서 삭제',
        parameters=[
            OpenApiParameter(name='spec_id', type=OpenApiTypes.INT, location=OpenApiParameter.PATH, description='삭제할 기획서 ID')
        ],
        responses={204: None}
    )
)
class RequirementDefinitionDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = RequirementDefinition.objects.all().select_related(
        'spec', 'project', 'status_code', 'created_by'
    ).prefetch_related('items__priority_code')
    serializer_class = RequirementDefinitionSerializer
    
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrPM]

    lookup_field = 'spec_id'
    lookup_url_kwarg = 'spec_id'

    def update(self, request, *args, **kwargs):
        new_status = request.data.get('status_code') or request.data.get('status_code_id')
        if new_status and not request.user.is_staff:
            if new_status in ['APPROVED', 'REJECTED']:
                return Response(
                    {"error": "FORBIDDEN", "details": "최종 승인(APPROVED) 및 반려(REJECTED)는 PM만 가능합니다."},
                    status=status.HTTP_403_FORBIDDEN
                )
            if new_status != 'PENDING_REVIEW':
                return Response(
                    {"error": "INVALID_STATUS", "details": "일반 유저는 검토 요청(PENDING_REVIEW) 상태로만 변경할 수 있습니다."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        old_status = serializer.instance.status_code_id
        instance = serializer.save()

        if old_status != 'APPROVED' and instance.status_code_id == 'APPROVED' and instance.project_id:
            PipelineHistory.objects.create(
                project=instance.project,
                spec=instance.spec,
                requirement=instance,
                step_type='REQ_DEFINED',
                title=f"요구사항정의서 확정: {instance.title}",
                description=f"승인자: {self.request.user.username} 사원",
                actor=self.request.user,
            )


class RequirementDefinitionSubmitReviewView(APIView):
    """요구사항 정의서 검토 요청 제출 (작성자 본인 검증)"""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='요구사항 정의서 검토 요청 제출',
        description='작성자 본인이 PM에게 요구사항 정의서 검토 요청(PENDING_REVIEW 상태 변경)을 제출합니다.',
        responses={
            200: OpenApiResponse(description='검토 요청 완료'),
            403: OpenApiResponse(description='작성자 본인만 검토 요청을 제출할 수 있습니다.')
        }
    )
    def post(self, request, spec_id):
        req_def = get_object_or_404(
            RequirementDefinition.objects.select_related('spec', 'created_by', 'spec__created_by'),
            spec_id=spec_id
        )
        
        # 작성자 검증
        created_by_user = get_target_author(req_def)
        if created_by_user and created_by_user != request.user:
            return Response(
                {"error": "FORBIDDEN", "details": "요구사항 정의서 작성자 본인만 검토 요청을 제출할 수 있습니다."},
                status=status.HTTP_403_FORBIDDEN
            )

        status_code = CommonCode.objects.filter(group_id='REQSPEC_STATUS', code_id='PENDING_REVIEW').first()
        if status_code:
            req_def.status_code = status_code
            req_def.save()

        notify_all_pms(
            f"'{req_def.title}' 요구사항 정의서 검토 요청이 도착했습니다.",
            type='info',
            link=f'/requirements/{spec_id}',
        )
        return Response({"message": "검토 요청이 완료되었습니다.", "data": RequirementDefinitionSerializer(req_def).data})


class RequirementDefinitionApproveView(APIView):
    """요구사항 정의서 승인 처리 (PM 전용)"""
    permission_classes = [permissions.IsAuthenticated, IsPMUser]

    @extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='요구사항 정의서 승인',
        description='PM이 요구사항 정의서를 승인(APPROVED 상태 변경) 처리합니다.',
        responses={200: OpenApiResponse(description='승인 완료')}
    )
    def post(self, request, spec_id):
        req_def = get_object_or_404(
            RequirementDefinition.objects.select_related('spec', 'created_by', 'spec__created_by'),
            spec_id=spec_id
        )
        status_code = CommonCode.objects.filter(group_id='REQSPEC_STATUS', code_id='APPROVED').first()
        if status_code:
            req_def.status_code = status_code
        req_def.save()

        # 히스토리 생성
        if req_def.project_id:
            PipelineHistory.objects.create(
                project=req_def.project,
                spec=req_def.spec,
                requirement=req_def,
                step_type='REQ_DEFINED',
                title=f"요구사항정의서 확정: {req_def.title}",
                description=f"승인자: {request.user.username} 사원",
                actor=request.user,
            )

        # 작성자 알림 발송
        created_by_user = get_target_author(req_def)
        if created_by_user:
            notify_user(
                created_by_user,
                f"'{req_def.title}' 요구사항 정의서가 승인되었습니다.",
                type='info',
                link=f'/requirements/{spec_id}',
            )

        return Response({"message": "요구사항 정의서가 승인되었습니다.", "data": RequirementDefinitionSerializer(req_def).data})


class RequirementDefinitionRejectView(APIView):
    """요구사항 정의서 반려 처리 (PM 전용)"""
    permission_classes = [permissions.IsAuthenticated, IsPMUser]

    @extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='요구사항 정의서 반려',
        description='PM이 요구사항 정의서를 반려(REJECTED 상태 변경) 처리합니다.',
        responses={200: OpenApiResponse(description='반려 완료')}
    )
    def post(self, request, spec_id):
        req_def = get_object_or_404(
            RequirementDefinition.objects.select_related('spec', 'created_by', 'spec__created_by'),
            spec_id=spec_id
        )
        status_code = CommonCode.objects.filter(group_id='REQSPEC_STATUS', code_id='REJECTED').first()
        if status_code:
            req_def.status_code = status_code
        req_def.save()

        # 작성자 알림 발송
        created_by_user = get_target_author(req_def)
        if created_by_user:
            notify_user(
                created_by_user,
                f"'{req_def.title}' 요구사항 정의서가 반려되었습니다.",
                type='error',
                link=f'/requirements/{spec_id}',
            )

        return Response({"message": "요구사항 정의서가 반려되었습니다.", "data": RequirementDefinitionSerializer(req_def).data})


class RequirementExtractView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='기획서 기반 AI 요구사항 재추출',
        parameters=[
            OpenApiParameter(name='spec_id', type=OpenApiTypes.INT, location=OpenApiParameter.PATH, description='AI 세부 항목을 재추출할 기획서 ID')
        ],
        responses={
            201: RequirementDefinitionSerializer,
            400: OpenApiResponse(description="잘못된 기획서 구조"),
            500: OpenApiResponse(description="AI 추출 처리 실패")
        }
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


class RequirementGenerateTasksView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['3단계 - 업무 배정'],
        summary='요구사항정의서 기반 업무 배분 제안 생성(AI, 미리보기)',
        parameters=[
            OpenApiParameter(name='spec_id', type=OpenApiTypes.INT, location=OpenApiParameter.PATH, description='업무 배분 제안을 생성할 기획서 ID')
        ],
        responses={
            200: OpenApiResponse(description='업무 배분 제안 목록 (suggestions)'),
            400: OpenApiResponse(description='업무 제안 생성 실패')
        }
    )
    def post(self, request, spec_id):
        from tasks.services import generate_task_suggestions
        result = generate_task_suggestions(spec_id)
        http_status = status.HTTP_200_OK if result.get("status") == "success" else status.HTTP_400_BAD_REQUEST
        return Response(result, status=http_status)


class RequirementConfirmTasksView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['3단계 - 업무 배정'],
        summary='업무 배분 제안 확정(DB 저장)',
        parameters=[
            OpenApiParameter(name='spec_id', type=OpenApiTypes.INT, location=OpenApiParameter.PATH, description='업무 배정을 확정할 기획서 ID')
        ],
        responses={
            200: OpenApiResponse(description='업무 배정 확정 결과'),
            400: OpenApiResponse(description='업무 배정 확정 실패')
        }
    )
    def post(self, request, spec_id):
        from tasks.services import confirm_task_assignments
        result = confirm_task_assignments(request.data.get("req_def_id"), request.data.get("assignments") or [])
        http_status = status.HTTP_200_OK if result.get("status") == "success" else status.HTTP_400_BAD_REQUEST
        return Response(result, status=http_status)


LOCKED_REQDEF_STATUSES = ('APPROVED', 'PENDING_REVIEW')


@extend_schema_view(
    get=extend_schema(tags=['2단계 - 요구사항 정의서'], summary='세부 요구사항 항목 목록 조회', responses={200: RequirementItemSerializer(many=True)}),
    post=extend_schema(tags=['2단계 - 요구사항 정의서'], summary='세부 요구사항 항목 직접 추가', responses={201: RequirementItemSerializer, 403: OpenApiResponse(description="승인/검토 중인 요구사항 정의서 잠금으로 추가 불가")})
)
class RequirementItemViewSet(generics.ListCreateAPIView):
    queryset = RequirementItem.objects.all().select_related('priority_code', 'req_def')
    serializer_class = RequirementItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        req_def_id = request.data.get('req_def')
        if req_def_id:
            req_def = RequirementDefinition.objects.filter(pk=req_def_id).select_related('status_code').first()
            if req_def and req_def.status_code_id in LOCKED_REQDEF_STATUSES:
                return Response(
                    {"error": "REQDEF_LOCKED", "details": "승인되었거나 검토 중인 요구사항정의서의 항목은 수정/삭제할 수 없습니다."},
                    status=status.HTTP_403_FORBIDDEN
                )
        return super().create(request, *args, **kwargs)


@extend_schema_view(
    get=extend_schema(tags=['2단계 - 요구사항 정의서'], summary='세부 요구사항 항목 단건 조회', responses={200: RequirementItemSerializer}),
    put=extend_schema(tags=['2단계 - 요구사항 정의서'], summary='세부 요구사항 항목 전체 수정', responses={200: RequirementItemSerializer, 403: OpenApiResponse(description="승인/검토 중인 요구사항 정의서 잠금으로 수정 불가")}),
    patch=extend_schema(tags=['2단계 - 요구사항 정의서'], summary='세부 요구사항 항목 부분 수정', responses={200: RequirementItemSerializer, 403: OpenApiResponse(description="승인/검토 중인 요구사항 정의서 잠금으로 수정 불가")}),
    delete=extend_schema(tags=['2단계 - 요구사항 정의서'], summary='세부 요구사항 항목 삭제', responses={204: None, 403: OpenApiResponse(description="승인/검토 중인 요구사항 정의서 잠금으로 삭제 불가")})
)
class RequirementItemDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = RequirementItem.objects.all().select_related('priority_code', 'req_def')
    serializer_class = RequirementItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def _check_not_locked(self, instance):
        req_def = instance.req_def
        if req_def and req_def.status_code_id in LOCKED_REQDEF_STATUSES:
            return Response(
                {"error": "REQDEF_LOCKED", "details": "승인되었거나 검토 중인 요구사항정의서의 항목은 수정/삭제할 수 없습니다."},
                status=status.HTTP_403_FORBIDDEN
            )
        return None

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        locked_response = self._check_not_locked(instance)
        if locked_response is not None:
            return locked_response
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        locked_response = self._check_not_locked(instance)
        if locked_response is not None:
            return locked_response
        return super().destroy(request, *args, **kwargs)
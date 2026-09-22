# requirements/views.py
import logging
import threading
import json
import html
import re
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.http import Http404
from django.utils import timezone
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

from requirements.models import RequirementDefinition, RequirementItem, RequirementExtractionJob, RequirementValidationReport
from requirements.serializers import (
    RequirementDefinitionSerializer,
    RequirementDefinitionCreateSerializer,
    RequirementItemSerializer,
    RequirementValidationReportSerializer,
)
from requirements.services import validate_requirement_definition, apply_requirement_validation
from meetings.models import SpecDocument
from common.models import CommonCode
from users.permissions import IsPMUser, IsOwnerOrPM  # PM 권한 검증
from notifications.services import notify_user, notify_all_pms  # 알림 서비스
from projects.models import PipelineHistory

# AI 에이전트 및 Pydantic 스키마 임포트
from requirement_draft.agent import generate_requirements
from requirement_draft.schemas import PlanDocument

logger = logging.getLogger(__name__)


def latest_requirement_definition(spec_id):
    return RequirementDefinition.objects.filter(spec_id=spec_id).order_by('-created_at', '-id').first()


def latest_requirement_definition_or_404(spec_id):
    req_def = latest_requirement_definition(spec_id)
    if req_def is None:
        raise Http404
    return req_def


def get_target_author(req_def):
    """요구사항 정의서 작성자 또는 기획서 작성자를 안전하게 반환하는 헬퍼 함수"""
    if getattr(req_def, 'created_by', None):
        return req_def.created_by
    if hasattr(req_def, 'spec') and getattr(req_def.spec, 'created_by', None):
        return req_def.spec.created_by
    return None


def _build_fallback_draft_result(req_def):
    """
    2026-09-17: RequirementTaskDraftView의 최후 수단 — TaskGenerationJob.result가
    없을 때(아주 오래된 데이터 등)만 쓴다. BACKLOG로 저장된 TaskAssignment 컬럼만으로
    최소한의 미리보기를 재구성한다. 적합도 서술(tech_fit/workload_fit/experience_fit
    개별 값)·팀 규모 추정·일정 브리핑 등은 애초에 TaskAssignment에 저장되는 컬럼이
    아니라서 복원할 방법이 없다 — assignment_reason(합쳐진 근거 문자열) 전체를
    tech_fit 한 자리에 몰아넣는 정도가 할 수 있는 최선이다.
    """
    from tasks.models import TaskAssignment, TaskStatusCode

    rows = TaskAssignment.objects.filter(
        req_item__req_def=req_def, status_code_id=TaskStatusCode.BACKLOG,
    ).select_related('req_item', 'assigned_user')
    prefix = f"RD{req_def.id}-"

    def _strip_prefix(value):
        return value[len(prefix):] if value and value.startswith(prefix) else value

    suggestions = []
    for r in rows:
        assignee_name = None
        if r.assigned_user:
            full_name = f"{r.assigned_user.last_name}{r.assigned_user.first_name}".strip()
            assignee_name = full_name or r.assigned_user.username
        suggestions.append({
            "unit_id": _strip_prefix(r.task_no),
            "source_req_id": r.req_item.req_code if r.req_item else "",
            "title": r.title,
            "description": r.description or "",
            "estimated_hours": r.estimated_hours,
            "difficulty_reason": r.difficulty_reason,
            "epic_no": r.epic_no,
            "epic_title": r.epic_title,
            "assignee_id": r.assigned_user_id,
            "assignee_name": assignee_name,
            "score": None,
            "tech_fit": r.assignment_reason,
            "workload_fit": None,
            "experience_fit": None,
            "review_required": False,
            "hold_explanation": None,
            "suggested_start_date": str(r.start_date) if r.start_date else None,
            "suggested_end_date": str(r.end_date) if r.end_date else None,
            "feature_area": None,
            "schedule_reason": None,
            "parent_task_id": _strip_prefix(r.parent_task),
        })

    return {
        "status": "success",
        "req_def_id": req_def.id,
        "suggestions": suggestions,
        "team_size_estimate": None,
        "complexity_assessment": None,
        "schedule_summary": None,
        "work_packages": [],
        "package_splits": [],
        "plan_review": {"held_units": [], "over_period_units": [], "needs_attention": False},
        "plan_briefing": {"risks": [], "checkpoints": []},
    }


def _parse_feature_lines(raw_features) -> list:
    """SpecDocument.key_features(TextField, 줄바꿈으로 구분된 자유 텍스트)를
    기능 항목별 줄로 분리한다.

    이전 코드는 `isinstance(raw_features, list)`를 조건으로 걸었는데,
    key_features는 실제로는 항상 str(TextField)라 이 조건이 절대 참이 될 수
    없었다 — 그래서 매번 else 분기(제목/개요 하나짜리 제네릭 요구사항)로만
    빠져, AI가 기능별로 요구사항을 쪼갤 근거 자체가 사라지고 있었다.
    meetings/services.py가 최초 생성 시 "• 제목: 설명" 줄 형식으로 채우지만,
    이후 PM이 ProposalTemplate 화면에서 자유 텍스트로 고칠 수 있으므로
    불릿 기호나 콜론 유무를 강제하지 않고 줄 단위로만 분리한다.
    """
    if isinstance(raw_features, list):
        return [str(f).strip() for f in raw_features if str(f).strip()]
    if not raw_features:
        return []
    text = str(raw_features)
    if re.search(r"<\s*p\b", text, flags=re.IGNORECASE):
        paragraphs = re.findall(
            r"<p[^>]*>(.*?)</p>", text, flags=re.IGNORECASE | re.DOTALL
        )
        lines = []
        pending_title = ""
        for paragraph in paragraphs:
            strong = re.fullmatch(
                r"\s*<strong[^>]*>(.*?)</strong>\s*",
                paragraph,
                flags=re.IGNORECASE | re.DOTALL,
            )
            plain = html.unescape(re.sub(r"<[^>]+>", " ", paragraph))
            plain = re.sub(r"\s+", " ", plain).strip()
            if not plain or plain == "PM 확인 사항":
                continue
            if strong:
                pending_title = plain
                continue
            if pending_title:
                lines.append(f"{pending_title}: {plain}")
                pending_title = ""
        if pending_title:
            lines.append(pending_title)
        if lines:
            return lines
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("•-*").strip()
        if not line or "회의에서 논의되지 않았습니다" in line:
            continue
        lines.append(line)
    return lines


def process_ai_requirement_extraction(spec_document, user, on_stage=None):
    """
    SpecDocument 기반으로 AI 에이전트를 실행하고
    RequirementDefinition 및 하위 RequirementItem들을 생성/저장하는 공통 헬퍼 함수

    on_stage: 있으면 각 단계 시작 시 사람이 읽을 라벨(str)로 호출한다(선택,
    2026-09-15 — 업무 배분/기획서 생성과 같은 진행 표시를 위해 도입).
    """
    def _stage(label: str) -> None:
        if on_stage:
            on_stage(label)

    spec_id = spec_document.spec_id

    # 1. SpecDocument DB 객체 -> PlanDocument Pydantic 스키마 변환 데이터 구성
    raw_goals = getattr(spec_document, "goals", [])
    if isinstance(raw_goals, list):
        goal_str = "\n".join([str(g) for g in raw_goals if g]) if raw_goals else getattr(spec_document, "overview", "요구사항 분석 및 기획서 도출")
    else:
        goal_str = str(raw_goals) if raw_goals else "요구사항 분석 및 기획서 도출"

    feature_lines = _parse_feature_lines(getattr(spec_document, "key_features", None))
    if feature_lines:
        requirements_input = []
        for i, line in enumerate(feature_lines):
            sep = ":" if ":" in line else ("：" if "：" in line else None)
            if sep:
                title, _, desc = line.partition(sep)
                title, desc = title.strip(), desc.strip()
            else:
                title, desc = line, line
            requirements_input.append({
                "id": f"REQ-{i+1:02d}",
                "title": title or line,
                "description": desc or line,
            })
    else:
        requirements_input = [
            {
                "id": "REQ-01",
                "title": getattr(spec_document, "title", "기본 요구사항"),
                "description": getattr(spec_document, "overview", "기획서 기반 기본 기능 요구사항")
            }
        ]

    final_decisions = getattr(spec_document, "final_decisions", None) or ""
    try:
        evidence_items = json.loads(getattr(spec_document, "evidence_items", "") or "{}")
        structured_decisions = evidence_items.get("final_decisions", {}).get(
            "structured_items", []
        )
        if structured_decisions:
            final_decisions = "\n".join(structured_decisions)
    except (TypeError, ValueError, json.JSONDecodeError):
        logger.warning("기획서 구조화 결정사항을 읽지 못해 화면용 본문을 사용합니다.")

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
        "final_decisions": final_decisions,
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
            plan_id=str(spec_document.spec_id),
            on_stage=on_stage,
        )
    except Exception as e:
        logger.exception(f"AI 요구사항 추출 실패 (spec_id: {spec_id}): {e}")
        raise RuntimeError(f"AI 요구사항 추출 중 오류가 발생했습니다: {str(e)}")

    # 4. DB 저장 및 기존 요구사항 정의서 연동 (트랜잭션)
    _stage("저장 중…")
    with transaction.atomic():
        draft_status = CommonCode.objects.filter(
            group_id='REQSPEC_STATUS',
            code_id='DRAFT'
        ).first()

        req_def = latest_requirement_definition(spec_document.spec_id)
        created = req_def is None
        if created:
            req_def = RequirementDefinition.objects.create(
                spec=spec_document,
                # SpecDocument엔 project 필드가 없다 — meeting을 거쳐야 프로젝트를 알 수 있다
                # (spec_document.project로 잘못 참조하면 hasattr()가 항상 False라 계속 None으로
                # 저장되는 버그가 있었음, 2026-09-08부터 발생).
                project=spec_document.meeting.project,
                title=f"{spec_document.title} - 요구사항 정의서",
                status_code=draft_status,
                created_by=user,
            )

        if not created:
            # get_or_create의 defaults는 "새로 만들 때"만 적용되고 기존 행은 절대 안 건드린다 —
            # 그래서 최초 생성 시점에 project가 None으로 저장된 요구사항정의서(예: 예전 버그로
            # project가 None이었거나, 회의록이 나중에 프로젝트에 연결된 경우)를 같은 기획서로
            # 재추출해도 project가 계속 None으로 남아있는 문제가 있었다(실제로 재현해서 확인 —
            # req_def 39: 최초 생성 이후 project가 None인 채로 남아있다가 재추출해도 그대로였음).
            # 매번 meeting.project를 신뢰 가능한 소스로 보고 다시 맞춰준다.
            if draft_status:
                req_def.status_code = draft_status
            if spec_document.meeting.project_id and req_def.project_id != spec_document.meeting.project_id:
                req_def.project = spec_document.meeting.project
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
                    related_feature=getattr(req_item, "related_feature", ""),
                    input_output=getattr(req_item, "input_output", ""),
                    acceptance_criteria=getattr(req_item, "acceptance_criteria", ""),
                    note=getattr(req_item, "note", ""),
                    source=getattr(getattr(req_item, "source", ""), "value", getattr(req_item, "source", "")),
                    review_status=getattr(getattr(req_item, "review_status", ""), "value", getattr(req_item, "review_status", "")),

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
        summary='요구사항 정의서 생성 (AI 세부항목 자동 추출) — 백그라운드 작업 시작',
        description=(
            '기획서 ID(`spec`)를 전달받아 백그라운드로 AI 세부 항목(RequirementItem) 자동 추출을 '
            '시작한다. 이 호출은 즉시 job_id만 반환하고, 실제 결과는 '
            'GET /api/requirements/extraction-jobs/{job_id}/ 를 폴링해서 받는다.'
        ),
        request=RequirementDefinitionCreateSerializer,
        responses={
            202: OpenApiResponse(description='작업 시작됨 (job_id)'),
            400: OpenApiResponse(description="잘못된 파라미터 또는 기획서 데이터"),
        }
    )
)
class RequirementDefinitionListCreateView(generics.ListCreateAPIView):
    queryset = RequirementDefinition.objects.all().order_by('-created_at', '-id')
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

        # 2026-09-15: AI 요구사항 추출이 LLM 호출(1회 + baseline 누락 시 최대
        # MAX_RETRIES회 재시도)이라 동기로 두면 오래 걸릴 수 있어(업무 배분/
        # 기획서 생성과 같은 이유), 백그라운드 실행 + 진행 단계 폴링으로 바꾼다.
        # PipelineHistory 로그(REQ_AI_GENERATED)는 워커(log_history=True)에서 남긴다.
        job = RequirementExtractionJob.objects.create(spec=spec_document, created_by=request.user)
        threading.Thread(
            target=_run_requirement_extraction_job, args=(job.id, request.user.id, True), daemon=True
        ).start()
        return Response({"status": "started", "job_id": str(job.id)}, status=status.HTTP_202_ACCEPTED)


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

    def get_object(self):
        obj = self.get_queryset().filter(spec_id=self.kwargs['spec_id']).order_by('-created_at', '-id').first()
        if obj is None:
            raise Http404
        self.check_object_permissions(self.request, obj)
        return obj

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
        req_def = latest_requirement_definition_or_404(spec_id)
        
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
        req_def = latest_requirement_definition_or_404(spec_id)
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
        req_def = latest_requirement_definition_or_404(spec_id)
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


class RequirementDefinitionValidateView(APIView):
    """기획서와 요구사항정의서를 비교 평가한다."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, req_def_id):
        req_def = get_object_or_404(RequirementDefinition.objects.select_related('spec__meeting'), pk=req_def_id)
        is_pm = request.user.is_staff or request.user.groups.filter(name='PM').exists()
        if req_def.spec.meeting.created_by_id != request.user.id and not is_pm:
            return Response({'detail': '작성자 또는 PM만 보고서를 조회할 수 있습니다.'}, status=status.HTTP_403_FORBIDDEN)
        report = RequirementValidationReport.objects.filter(
            Q(requirement_definition=req_def) | Q(applied_definition=req_def)
        ).order_by('-created_at').first()
        if report is None:
            return Response({'detail': '저장된 검증 보고서가 없습니다.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(RequirementValidationReportSerializer(report).data)

    def post(self, request, req_def_id):
        req_def = get_object_or_404(
            RequirementDefinition.objects.select_related('spec__meeting').prefetch_related('items'),
            pk=req_def_id,
        )
        is_pm = request.user.is_staff or request.user.groups.filter(name='PM').exists()
        if req_def.spec.meeting.created_by_id != request.user.id and not is_pm:
            return Response({'detail': '작성자 또는 PM만 검증할 수 있습니다.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            report = validate_requirement_definition(req_def, request.user)
        except Exception as exc:
            return Response({'detail': f'요구사항정의서 검증 중 오류가 발생했습니다: {exc}'}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(RequirementValidationReportSerializer(report).data, status=status.HTTP_201_CREATED)


class RequirementValidationReportApplyView(APIView):
    """AI 보완안을 원본을 보존한 새 요구사항정의서 버전으로 만든다."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, report_id):
        report = get_object_or_404(
            RequirementValidationReport.objects.select_related(
                'requirement_definition__spec__meeting', 'applied_definition'
            ), pk=report_id,
        )
        meeting = report.requirement_definition.spec.meeting
        is_pm = request.user.is_staff or request.user.groups.filter(name='PM').exists()
        if meeting.created_by_id != request.user.id and not is_pm:
            return Response({'detail': '작성자 또는 PM만 적용할 수 있습니다.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            revised = apply_requirement_validation(report)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'message': '보완사항을 적용한 새 요구사항정의서 버전을 생성했습니다.',
            'requirement_definition': RequirementDefinitionSerializer(revised).data,
        })


class RequirementExtractView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='기획서 기반 AI 요구사항 재추출 — 백그라운드 작업 시작',
        parameters=[
            OpenApiParameter(name='spec_id', type=OpenApiTypes.INT, location=OpenApiParameter.PATH, description='AI 세부 항목을 재추출할 기획서 ID')
        ],
        responses={
            202: OpenApiResponse(description='작업 시작됨 (job_id)'),
            400: OpenApiResponse(description="잘못된 기획서 구조"),
        }
    )
    def post(self, request, spec_id):
        spec_document = get_object_or_404(SpecDocument, spec_id=spec_id)
        # 재추출은 이미 있는 요구사항정의서를 다시 뽑는 것이라(REQ_AI_GENERATED
        # 로그는 최초 생성 시점에만 남긴다는 기존 규칙과 동일하게) 히스토리를
        # 남기지 않는다 — log_history=False.
        job = RequirementExtractionJob.objects.create(spec=spec_document, created_by=request.user)
        threading.Thread(
            target=_run_requirement_extraction_job, args=(job.id, request.user.id, False), daemon=True
        ).start()
        return Response({"status": "started", "job_id": str(job.id)}, status=status.HTTP_202_ACCEPTED)


def _run_requirement_extraction_job(job_id, actor_user_id, log_history: bool):
    """
    RequirementDefinitionListCreateView.create / RequirementExtractView.post가
    스레드로 띄우는 실제 작업 — _run_generate_tasks_job/_run_analyze_job과 동일한
    패턴(2026-09-15). log_history는 호출부에 따라 다르다: 최초 생성(create)만
    PipelineHistory에 REQ_AI_GENERATED를 남기고, 재추출(extract)은 남기지 않는다
    (기존 동기 코드의 동작을 그대로 유지).
    """
    from django.db import close_old_connections
    from django.contrib.auth import get_user_model

    close_old_connections()
    try:
        RequirementExtractionJob.objects.filter(pk=job_id).update(
            status=RequirementExtractionJob.STATUS_RUNNING, updated_at=timezone.now()
        )

        def on_stage(label):
            RequirementExtractionJob.objects.filter(pk=job_id).update(
                stage=label[:100], updated_at=timezone.now()
            )

        job = RequirementExtractionJob.objects.select_related('spec').get(pk=job_id)
        actor = get_user_model().objects.filter(pk=actor_user_id).first()
        req_def = process_ai_requirement_extraction(job.spec, actor, on_stage=on_stage)
    except ValueError as ve:
        RequirementExtractionJob.objects.filter(pk=job_id).update(
            status=RequirementExtractionJob.STATUS_ERROR, error_message=str(ve), updated_at=timezone.now()
        )
        close_old_connections()
        return
    except Exception as e:
        logger.exception("요구사항정의서 생성 작업 실패 (job_id=%s)", job_id)
        RequirementExtractionJob.objects.filter(pk=job_id).update(
            status=RequirementExtractionJob.STATUS_ERROR, error_message=str(e), updated_at=timezone.now()
        )
        close_old_connections()
        return

    # 파이프라인 이력 로그 생성 — "요구사항정의서 생성" 버튼(AI 호출) 시점.
    # 확정 시점의 REQ_DEFINED와 구분되는 별도 step_type이라 히스토리
    # "에이전트" 탭에 실제 AI 실행으로 잡힌다(사람이 누른 확정과 혼동 방지).
    if log_history and req_def.project_id:
        PipelineHistory.objects.create(
            project=req_def.project,
            spec=job.spec,
            requirement=req_def,
            step_type='REQ_AI_GENERATED',
            title=f"요구사항정의서 생성: {req_def.title}",
            description=f"실행자: {actor.username if actor else '알 수 없음'} 사원",
            actor=actor,
        )

    RequirementExtractionJob.objects.filter(pk=job_id).update(
        status=RequirementExtractionJob.STATUS_SUCCESS,
        result=RequirementDefinitionSerializer(req_def).data,
        stage="완료",
        updated_at=timezone.now(),
    )
    close_old_connections()


class RequirementExtractionJobStatusView(APIView):
    """요구사항정의서 생성 작업 진행 상태 조회(폴링) — GET /api/requirements/extraction-jobs/{job_id}/"""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['2단계 - 요구사항 정의서'],
        summary='요구사항정의서 생성 작업 진행 상태 조회(폴링)',
        parameters=[
            OpenApiParameter(name='job_id', type=OpenApiTypes.STR, location=OpenApiParameter.PATH, description='RequirementDefinitionListCreateView/RequirementExtractView가 반환한 job_id')
        ],
        responses={200: OpenApiResponse(description='작업 상태(진행 중/완료/실패)')}
    )
    def get(self, request, job_id):
        job = get_object_or_404(RequirementExtractionJob, pk=job_id)
        payload = {"status": job.status, "stage": job.stage}
        if job.status == RequirementExtractionJob.STATUS_SUCCESS:
            payload["result"] = job.result
        elif job.status == RequirementExtractionJob.STATUS_ERROR:
            payload["message"] = job.error_message
        return Response(payload)


def _run_generate_tasks_job(job_id, actor_user_id):
    """
    RequirementGenerateTasksView.post가 스레드로 띄우는 실제 작업. 순차 LLM
    호출 여러 개라 1~수 분 걸리는 게 정상이라(2026-09-14 "너무 오래 걸림" 문의
    확인), 요청-응답 안에서 동기로 기다리는 대신 여기서 백그라운드로 돌리고
    TaskGenerationJob에 진행 단계를 기록한다 — 프론트는 job_id로 폴링한다.

    스레드 안에서 도는 함수라 요청 컨텍스트(request.user)를 못 쓴다 — actor는
    id로 넘겨받아 여기서 다시 조회한다. Django 커넥션은 스레드마다 별도라
    시작/종료 시 close_old_connections()로 정리한다(그대로 두면 스레드가 오래
    끊긴 커넥션을 계속 붙들 수 있음).
    """
    from django.db import close_old_connections
    from django.contrib.auth import get_user_model
    from tasks.models import TaskGenerationJob
    from tasks.services import generate_task_suggestions

    close_old_connections()
    try:
        TaskGenerationJob.objects.filter(pk=job_id).update(
            status=TaskGenerationJob.STATUS_RUNNING, updated_at=timezone.now()
        )

        def on_stage(label):
            TaskGenerationJob.objects.filter(pk=job_id).update(
                stage=label[:100], updated_at=timezone.now()
            )

        job = TaskGenerationJob.objects.get(pk=job_id)
        result = generate_task_suggestions(job.spec_id, on_stage=on_stage)
    except Exception as e:
        logger.exception("업무 배분 실행 작업 실패 (job_id=%s)", job_id)
        TaskGenerationJob.objects.filter(pk=job_id).update(
            status=TaskGenerationJob.STATUS_ERROR, error_message=str(e), updated_at=timezone.now()
        )
        close_old_connections()
        return

    # 파이프라인 이력 로그 생성 — "업무 배분 AI 추천" 버튼 시점. 2026-09-15부터
    # generate_task_suggestions() 안에서 이 결과를 TaskAssignment(BACKLOG, 초안)로
    # 바로 저장하지만, 그건 어디까지나 "PM 확정 전 안전 보관"이지 확정이 아니다 —
    # PM이 "배분 확정"을 눌러야 RequirementConfirmTasksView가 PENDING_APPROVAL로
    # 전환하며 TASK_ASSIGNED로 별도 로그를 남긴다. 여기서 남기지 않으면 에이전트
    # 탭에서 "AI 추천이 실행됐다"는 이 시점 자체가 보이지 않는다.
    if result.get("status") == "success" and result.get("req_def_id"):
        req_def = RequirementDefinition.objects.filter(pk=result["req_def_id"]).select_related('spec').first()
        if req_def and req_def.project_id:
            actor = get_user_model().objects.filter(pk=actor_user_id).first()
            PipelineHistory.objects.create(
                project=req_def.project,
                spec=req_def.spec,
                requirement=req_def,
                step_type='TASK_AI_SUGGESTED',
                title=f"업무 배분 AI 추천: {req_def.title}",
                description=f"실행자: {actor.username if actor else '알 수 없음'} 사원",
                actor=actor,
            )

    if result.get("status") == "success":
        TaskGenerationJob.objects.filter(pk=job_id).update(
            status=TaskGenerationJob.STATUS_SUCCESS, result=result, stage="완료", updated_at=timezone.now()
        )
    else:
        TaskGenerationJob.objects.filter(pk=job_id).update(
            status=TaskGenerationJob.STATUS_ERROR,
            error_message=result.get("message") or "알 수 없는 오류",
            updated_at=timezone.now(),
        )
    close_old_connections()


class RequirementGenerateTasksView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPMUser]

    @extend_schema(
        tags=['3단계 - 업무 배정'],
        summary='요구사항정의서 기반 업무 배분 제안 생성(AI, 미리보기) — 백그라운드 작업 시작',
        description=(
            '순차 LLM 호출 여러 개라 1~수 분 걸릴 수 있어 동기로 기다리지 않는다. '
            '이 호출은 즉시 job_id만 반환하고, 실제 결과는 '
            'GET /api/requirements/generate-tasks-jobs/{job_id}/ 를 폴링해서 받는다.'
        ),
        parameters=[
            OpenApiParameter(name='spec_id', type=OpenApiTypes.INT, location=OpenApiParameter.PATH, description='업무 배분 제안을 생성할 기획서 ID')
        ],
        responses={
            202: OpenApiResponse(description='작업 시작됨 (job_id)'),
            404: OpenApiResponse(description='기획서를 찾을 수 없음'),
        }
    )
    def post(self, request, spec_id):
        from meetings.models import SpecDocument
        from tasks.models import TaskGenerationJob

        if not SpecDocument.objects.filter(pk=spec_id).exists():
            return Response({"error": "기획서를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        job = TaskGenerationJob.objects.create(spec_id=spec_id, created_by=request.user)
        threading.Thread(
            target=_run_generate_tasks_job, args=(job.id, request.user.id), daemon=True
        ).start()
        return Response({"status": "started", "job_id": str(job.id)}, status=status.HTTP_202_ACCEPTED)


class RequirementGenerateTasksJobStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPMUser]

    @extend_schema(
        tags=['3단계 - 업무 배정'],
        summary='업무 배분 실행 작업 진행 상태 조회(폴링)',
        parameters=[
            OpenApiParameter(name='job_id', type=OpenApiTypes.STR, location=OpenApiParameter.PATH, description='RequirementGenerateTasksView가 반환한 job_id')
        ],
        responses={200: OpenApiResponse(description='작업 상태(진행 중/완료/실패)')}
    )
    def get(self, request, job_id):
        from tasks.models import TaskGenerationJob
        job = get_object_or_404(TaskGenerationJob, pk=job_id)
        payload = {"status": job.status, "stage": job.stage}
        if job.status == TaskGenerationJob.STATUS_SUCCESS:
            payload["result"] = job.result
        elif job.status == TaskGenerationJob.STATUS_ERROR:
            payload["message"] = job.error_message
        return Response(payload)


class RequirementConfirmTasksView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPMUser]

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


class RequirementTaskDraftView(APIView):
    """
    2026-09-17: 새로고침 대비 — "업무 배분 실행" 미리보기(documents/page.tsx의
    taskDrafts)는 순수 React state라 새로고침하면 사라진다. 그런데 그 결과는 이미
    두 곳에 남아있다:
      1) TaskAssignment(BACKLOG) — 제목/담당자/일정/Epic 등 뼈대만
      2) TaskGenerationJob.result — 생성 당시 generate_task_suggestions()가 반환한
         전체 값 그대로(적합도 서술·팀 규모 추정·일정 브리핑 등 포함)
    BACKLOG가 아직 남아있다는 건 PM이 아직 확정하지 않았다는 뜻이므로, 그때만 가장
    최근 성공한 TaskGenerationJob.result를 그대로 돌려줘 화면을 원래대로 복원한다.
    이미 확정됐거나(BACKLOG가 confirm 시점에 삭제됨) 애초에 생성한 적이 없으면
    has_draft=False — 이 경우 프론트는 기존처럼 빈 화면/실제 배정 목록을 보여준다.
    """
    permission_classes = [permissions.IsAuthenticated, IsPMUser]

    @extend_schema(
        tags=['3단계 - 업무 배정'],
        summary='저장된 업무 배분 초안(BACKLOG) 복원',
        description='아직 확정하지 않은 BACKLOG 초안이 있으면 생성 당시의 전체 결과를 그대로 돌려준다(새로고침 복원용).',
        parameters=[
            OpenApiParameter(name='spec_id', type=OpenApiTypes.INT, location=OpenApiParameter.PATH, description='기획서 ID')
        ],
        responses={200: OpenApiResponse(description='has_draft + (있으면) generate_task_suggestions와 동일한 모양의 result')}
    )
    def get(self, request, spec_id):
        from tasks.models import TaskAssignment, TaskGenerationJob, TaskStatusCode

        req_def = RequirementDefinition.objects.filter(spec_id=spec_id).order_by('-id').first()
        if not req_def:
            return Response({"has_draft": False})

        has_backlog = TaskAssignment.objects.filter(
            req_item__req_def=req_def, status_code_id=TaskStatusCode.BACKLOG,
        ).exists()
        if not has_backlog:
            return Response({"has_draft": False})

        job = (
            TaskGenerationJob.objects
            .filter(spec_id=spec_id, status=TaskGenerationJob.STATUS_SUCCESS)
            .order_by('-created_at')
            .first()
        )
        if job and job.result and job.result.get("req_def_id") == req_def.id:
            return Response({"has_draft": True, "result": job.result})

        return Response({"has_draft": True, "result": _build_fallback_draft_result(req_def)})


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

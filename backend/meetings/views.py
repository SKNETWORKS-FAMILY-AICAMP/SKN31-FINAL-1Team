#meetings/views.py
import json
import re
import html
from django.shortcuts import get_object_or_404
from rest_framework import status, permissions, generics, parsers
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse, OpenApiTypes

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

from pypdf import PdfReader

from meetings.models import MeetingNote, SpecDocument
from meetings.serializers import (
    MeetingNoteSerializer,
    MeetingNoteCreateSerializer,
    SpecDocumentSerializer,
)
from common.models import CommonCode
from users.permissions import IsPMUser, IsOwnerOrPM  # IsOwnerOrPM 추가
from notifications.services import notify_user, notify_all_pms
from projects.models import PipelineHistory

# AI 모듈 불러오기
from meeting_analysis.node import run as analyze_meeting
from plan_draft.agent import run as generate_plan


# ==========================================
# 1. 회의록(MeetingNote) API Views
# ==========================================

class MeetingNoteListCreateView(generics.ListCreateAPIView):
    """
    회의록 목록 조회 및 작성 API
    GET/POST /api/meetings/notes/
    """
    queryset = MeetingNote.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return MeetingNoteCreateSerializer
        return MeetingNoteSerializer

    @extend_schema(
        tags=['1단계 - 회의록'],
        summary='회의록 목록 조회',
        description='등록된 회의록 전체 목록을 조회합니다.',
        responses={200: MeetingNoteSerializer(many=True)}
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        tags=['1단계 - 회의록'],
        summary='회의록 신규 작성',
        description='새로운 회의록을 작성 및 등록합니다.',
        request=MeetingNoteCreateSerializer,
        responses={201: MeetingNoteSerializer}
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save(created_by=request.user)

        # 파이프라인 이력 로그 생성
        if instance.project_id:
            PipelineHistory.objects.create(
                project=instance.project,
                meeting=instance,
                step_type='MEETING_REGISTERED',
                title=f"회의록 등록: {instance.title}",
                description=f"작성자: {request.user.username} 사원",
                actor=request.user,
            )

        response_serializer = MeetingNoteSerializer(instance)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class MeetingNoteDetailView(generics.RetrieveUpdateDestroyAPIView):
    """회의록 상세 조회, 수정, 삭제 (작성자 본인 또는 PM만 수정/삭제 가능)"""
    queryset = MeetingNote.objects.all()
    serializer_class = MeetingNoteSerializer
    # [수정] 작성자 또는 PM(is_staff=True)만 수정/삭제 가능하도록 IsOwnerOrPM 적용
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrPM]

    @extend_schema(
        tags=['1단계 - 회의록'],
        summary='회의록 상세 조회',
        description='특정 회의록의 상세 정보를 조회합니다.',
        responses={200: MeetingNoteSerializer}
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        tags=['1단계 - 회의록'],
        summary='회의록 수정',
        description='특정 회의록 정보(전체 수정)를 갱신합니다.',
        responses={200: MeetingNoteSerializer}
    )
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)

    @extend_schema(
        tags=['1단계 - 회의록'],
        summary='회의록 부분 수정',
        description='특정 회의록 정보(부분 수정)를 갱신합니다.',
        responses={200: MeetingNoteSerializer}
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    @extend_schema(
        tags=['1단계 - 회의록'],
        summary='회의록 삭제',
        description='특정 회의록을 삭제합니다.',
        responses={204: None}
    )
    def delete(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)


class MeetingNoteAnalyzeView(APIView):
    """
    회의록 AI 분석 및 기획 초안 자동 생성 API
    POST /api/meetings/notes/{id}/analyze/
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['1단계 - 회의록'],
        summary='회의록 AI 분석 및 기획서 자동 생성',
        description='회의록 내용을 AI로 분석하여 요약 및 기획서 초안(SpecDocument)을 자동 생성합니다.',
        responses={
            200: OpenApiResponse(description='분석 완료 및 기획서 생성 성공'),
            500: OpenApiResponse(description='AI 분석 중 오류 발생')
        }
    )
    def post(self, request, pk):
        meeting = get_object_or_404(MeetingNote, pk=pk)

        # 작성자 본인 확인
        if meeting.created_by != request.user:
            return Response(
                {"error": "작성자 본인만 검토 요청을 할 수 있습니다."}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # 1. 상태 업데이트: AI 분석 중
        meeting.status = MeetingNote.Status.PROCESSING
        meeting.save()

        try:
            # 2. AI 노드 ①: 회의록 분석
            analysis_result = analyze_meeting(meeting.content, str(meeting.pk))
            structured_data = analysis_result.data if hasattr(analysis_result, 'data') else analysis_result

            # 3. AI 노드 ②: 기획서 초안 생성
            proposal_id = f"PLN-{meeting.pk:03d}"
            doc = generate_plan(structured_data, proposal_id)
            
            # Pydantic 또는 객체/dict 변환
            if hasattr(doc, 'model_dump'):
                plan_dict = doc.model_dump(mode="json")
            elif hasattr(doc, 'dict'):
                plan_dict = doc.dict()
            elif isinstance(doc, dict):
                plan_dict = doc
            else:
                plan_dict = {}

            # 4. 회의록 상태 업데이트
            summary_val = structured_data.get('summary') if isinstance(structured_data, dict) else None
            meeting.summary_content = summary_val or f"[{meeting.title}] AI 분석이 완료되었습니다."
            meeting.status = MeetingNote.Status.REVIEWED
            meeting.save()

            def strip_html_tags(text):
                if not text:
                    return ""
                text_str = str(text)
                decoded_text = html.unescape(text_str)
                clean_text = re.sub(r'<[^>]+>', ' ', decoded_text)
                clean_text = re.sub(r'[ \t]+', ' ', clean_text)
                clean_text = re.sub(r'\n\s*\n', '\n', clean_text)
                return clean_text.strip()

            # ai/plan_draft/schemas.py의 SECTION_SPEC(노드②의 설계도)과 동일한 key ↔
            # SpecDocument 필드명 매핑. 근거자료(evidence_data)도 이 키로 저장해야 프론트
            # (documents/page.tsx의 EVIDENCE_KEY_ALIASES)가 올바른 섹션에 붙여준다.
            SECTION_KEY_TO_FIELD = {
                'overview': 'overview',
                'problem': 'problem_definition',
                'users': 'target_users',
                'features': 'key_features',
                'scenarios': 'user_scenarios',
                'tech_scope': 'tech_stack',
                'decisions': 'final_decisions',
            }

            sections_map = {}
            evidence_map = {}
            for sec in (plan_dict.get('sections') or []):
                if not isinstance(sec, dict):
                    continue
                sec_key = sec.get('key')
                if not sec_key or not isinstance(sec_key, str):
                    continue

                content = sec.get('content_html') or ""
                if not content and isinstance(sec.get('items'), list):
                    content = "\n".join(f"- {item}" for item in sec['items'] if isinstance(item, (str, int)))
                if not content and isinstance(sec.get('features'), list):
                    lines = []
                    for f in sec['features']:
                        if isinstance(f, dict):
                            lines.append(f"• {f.get('title', '')}: {f.get('description', '')}")
                    content = "\n".join(lines)

                sections_map[sec_key] = content

                # PlanSection.evidence(VerifiedEvidence 목록)는 노드①이 이미 원문 대조를
                # 마친 근거라 status를 갖는다 — 회의록에 실제로 없는 문장을 "근거"로 보여주는
                # 걸 막기 위해(환각 방지 원칙) status="verified"인 것만 채택한다.
                quotes = [
                    e.get('quote') for e in (sec.get('evidence') or [])
                    if isinstance(e, dict) and e.get('status') == 'verified' and e.get('quote')
                ]
                field_name = SECTION_KEY_TO_FIELD.get(sec_key)
                if quotes and field_name:
                    evidence_map[field_name] = "\n".join(f"- {q}" for q in quotes)

            NOT_DISCUSSED = "회의에서 논의되지 않았습니다."

            def section_or_not_discussed(key):
                val = sections_map.get(key, "")
                return val if val.strip() else NOT_DISCUSSED

            spec_defaults = {
                'title': f"{meeting.title} - 기획 초안",
                'overview': section_or_not_discussed('overview'),
                'problem_definition': section_or_not_discussed('problem'),
                'target_users': section_or_not_discussed('users'),
                'key_features': section_or_not_discussed('features'),
                'user_scenarios': section_or_not_discussed('scenarios'),
                'tech_stack': section_or_not_discussed('tech_scope'),
                'final_decisions': section_or_not_discussed('decisions'),
            }
            if evidence_map:
                spec_defaults['evidence_data'] = json.dumps(evidence_map, ensure_ascii=False)

            period_match = re.search(
                r'(\d{4}-\d{2}-\d{2})\s*(?:~|-|부터)\s*(\d{4}-\d{2}-\d{2})',
                meeting.content or "",
            )
            if period_match:
                spec_defaults['period_start'] = period_match.group(1)
                spec_defaults['period_end'] = period_match.group(2)

            # 6. 기존 기획서가 있다면 필드 값 업데이트
            spec, created = SpecDocument.objects.update_or_create(
                meeting=meeting,
                defaults=spec_defaults
            )

            # 파이프라인 이력 로그 생성 — "기획서 생성" 버튼(AI 호출) 시점.
            # 승인 시점의 SPEC_GENERATED와 구분되는 별도 step_type이라 히스토리
            # "에이전트" 탭에 실제 AI 실행으로 잡힌다(사람이 누른 승인과 혼동 방지).
            if meeting.project_id:
                PipelineHistory.objects.create(
                    project=meeting.project,
                    meeting=meeting,
                    spec=spec,
                    step_type='SPEC_AI_GENERATED',
                    title=f"기획서 생성: {spec.title}",
                    description=f"실행자: {request.user.username} 사원",
                    actor=request.user,
                )

            return Response({
                "message": "회의록 AI 분석 및 기획서 초안 생성이 완료되었습니다.",
                "meeting": MeetingNoteSerializer(meeting).data,
                "created_spec": SpecDocumentSerializer(spec).data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            meeting.status = MeetingNote.Status.DRAFT
            meeting.save()
            return Response(
                {"error": "AI 기획서 생성 중 오류가 발생했습니다.", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ==========================================
# 2. 기획서(SpecDocument) API Views
# ==========================================

class SpecDocumentListCreateView(generics.ListCreateAPIView):
    """기획서 목록 조회 및 생성"""
    queryset = SpecDocument.objects.all()
    serializer_class = SpecDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['2단계 - 기획서'],
        summary='기획서 목록 조회',
        description='등록된 전체 기획서 목록을 조회합니다.',
        responses={200: SpecDocumentSerializer(many=True)}
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        tags=['2단계 - 기획서'],
        summary='기획서 생성',
        description='새로운 기획서를 수동으로 작성 및 생성합니다.',
        responses={201: SpecDocumentSerializer}
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class SpecDocumentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """기획서 상세 조회, 수정, 삭제 (작성자 본인 또는 PM만 가능)"""
    queryset = SpecDocument.objects.all()
    serializer_class = SpecDocumentSerializer
    # [수정] 작성자 또는 PM(is_staff=True)만 수정/삭제 가능하도록 IsOwnerOrPM 적용
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrPM]

    @extend_schema(
        tags=['2단계 - 기획서'],
        summary='기획서 상세 조회',
        description='특정 기획서의 상세 정보를 조회합니다.',
        responses={200: SpecDocumentSerializer}
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        tags=['2단계 - 기획서'],
        summary='기획서 전체 수정',
        description='특정 기획서의 모든 정보를 수정합니다.',
        responses={200: SpecDocumentSerializer}
    )
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)

    @extend_schema(
        tags=['2단계 - 기획서'],
        summary='기획서 부분 수정',
        description='특정 기획서의 일부 정보를 수정합니다.',
        responses={200: SpecDocumentSerializer}
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    @extend_schema(
        tags=['2단계 - 기획서'],
        summary='기획서 삭제',
        description='특정 기획서를 삭제합니다.',
        responses={204: None}
    )
    def delete(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)


class SpecDocumentReviewView(APIView):
    """기획서 검토 의견 작성/수정 (PM 권한)"""
    # [수정] 코멘트 남기기 및 리뷰어 지정은 PM 전용
    permission_classes = [permissions.IsAuthenticated, IsPMUser]

    @extend_schema(
        tags=['2단계 - 기획서'],
        summary='기획서 검토 코멘트 남기기',
        description='기획서에 검토 코멘트(review_comment)를 작성하고 검토자를 지정합니다.',
        responses={200: SpecDocumentSerializer}
    )
    def post(self, request, pk):
        spec = get_object_or_404(SpecDocument, pk=pk)
        review_comment = request.data.get('review_comment', '')
        
        spec.review_comment = review_comment
        spec.reviewer = request.user
        spec.save()
        
        return Response(SpecDocumentSerializer(spec).data, status=status.HTTP_200_OK)


class SpecDocumentSubmitReviewView(APIView):
    """기획서 검토 요청 전송 (pk 기준 - 작성자 검증 적용)"""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['2단계 - 기획서'],
        summary='기획서 검토 요청 제출',
        description='기획서 작성자 본인이 PM에게 검토 요청을 제출합니다.',
        responses={
            200: OpenApiResponse(description='검토 요청 완료'),
            403: OpenApiResponse(description='작성자 본인만 검토 요청을 할 수 있습니다.')
        }
    )
    def post(self, request, pk):
        spec = get_object_or_404(SpecDocument, pk=pk)
        
        # 작성자 검증
        created_by_user = getattr(spec, 'created_by', None) or getattr(spec.meeting, 'created_by', None)
        if created_by_user and created_by_user != request.user:
            return Response(
                {"error": "FORBIDDEN", "details": "기획서 작성자 본인만 검토 요청을 제출할 수 있습니다."},
                status=status.HTTP_403_FORBIDDEN
            )

        # [수정] CommonCode 검색 조건을 SPEC_STATUS 그룹의 PENDING_REVIEW로 통일
        pending_status = CommonCode.objects.filter(group_id='SPEC_STATUS', code_id='PENDING_REVIEW').first() \
                         or CommonCode.objects.filter(code_id='PROPOSAL_PENDING_REVIEW').first()
        
        if pending_status:
            spec.status_code = pending_status
            spec.save()

        notify_all_pms(
            message=f"'{spec.title}' 기획서 검토요청이 도착했습니다.",
            type='info',
            link='/documents',
        )
        return Response({"message": "검토 요청이 완료되었습니다.", "spec": SpecDocumentSerializer(spec).data})

    patch = post


class SubmitReviewView(APIView):
    """
    POST /api/meetings/specs/{spec_id}/submit-review/
    기획서 검토 요청 API (spec_id 기준 - 작성자 본인만 가능)
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['1단계 - 기획서/회의록'],
        summary='기획서 검토 요청 (spec_id)',
        description='기획서 작성자 본인이 PM에게 검토 요청을 보냅니다.',
        parameters=[
            OpenApiParameter(
                name='spec_id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description='검토 요청할 기획서 ID'
            )
        ],
        responses={
            200: SpecDocumentSerializer,
            403: OpenApiResponse(description="작성자 본인만 검토 요청을 보낼 수 있습니다."),
            400: OpenApiResponse(description="잘못된 요청 또는 상태 변환 불가")
        }
    )
    def post(self, request, spec_id):
        spec = get_object_or_404(SpecDocument, spec_id=spec_id)

        # 작성자 본인 확인
        created_by_user = getattr(spec, 'created_by', None) or getattr(spec.meeting, 'created_by', None)
        if created_by_user and created_by_user != request.user:
            return Response(
                {"error": "FORBIDDEN", "details": "기획서 작성자 본인만 검토 요청을 제출할 수 있습니다."},
                status=status.HTTP_403_FORBIDDEN
            )

        pending_status = CommonCode.objects.filter(group_id='SPEC_STATUS', code_id='PENDING_REVIEW').first() \
                         or CommonCode.objects.filter(code_id='PROPOSAL_PENDING_REVIEW').first()

        if not pending_status:
            return Response(
                {"error": "INVALID_STATUS_CODE", "details": "PENDING_REVIEW 코드가 존재하지 않습니다."},
                status=status.HTTP_400_BAD_REQUEST
            )

        spec.status_code = pending_status
        spec.save()

        notify_all_pms(
            message=f"'{spec.title}' 기획서의 검토 요청이 등록되었습니다.",
            type='info',
            link=f"/meetings/specs/{spec.spec_id}"
        )

        serializer = SpecDocumentSerializer(spec)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SpecDocumentApproveView(APIView):
    """기획서 승인 처리 (PM 전용)"""
    permission_classes = [permissions.IsAuthenticated, IsPMUser]

    @extend_schema(
        tags=['2단계 - 기획서'],
        summary='기획서 승인',
        description='PM이 기획서를 승인 처리합니다.',
        responses={200: OpenApiResponse(description='승인 완료')}
    )
    def post(self, request, pk):
        spec = get_object_or_404(SpecDocument, pk=pk)
        
        status_code = CommonCode.objects.filter(group_id='SPEC_STATUS', code_id='APPROVED').first() \
                      or CommonCode.objects.filter(code_id='PROPOSAL_APPROVED').first()
        if status_code:
            spec.status_code = status_code
        
        spec.reviewer = request.user
        spec.review_comment = request.data.get('comment', spec.review_comment)
        spec.save()
        
        created_by_user = getattr(spec, 'created_by', None) or getattr(spec.meeting, 'created_by', None)
        if created_by_user:
            notify_user(
                created_by_user,
                f"'{spec.title}' 기획서가 승인되었습니다.",
                type='info',
                link='/documents',
            )

        # 파이프라인 이력 로그 생성 (팀원 커밋으로 유실됐던 로직 복구)
        if spec.meeting.project_id:
            PipelineHistory.objects.create(
                project=spec.meeting.project,
                meeting=spec.meeting,
                spec=spec,
                step_type='SPEC_GENERATED',
                title=f"기획서 승인: {spec.title}",
                description=f"승인자: {request.user.username} 사원",
                actor=request.user,
            )

        return Response({"message": "기획서가 승인되었습니다.", "spec": SpecDocumentSerializer(spec).data})


class SpecDocumentRejectView(APIView):
    """기획서 반려 처리 (PM 전용)"""
    permission_classes = [permissions.IsAuthenticated, IsPMUser]

    @extend_schema(
        tags=['2단계 - 기획서'],
        summary='기획서 반려',
        description='PM이 기획서를 반려 처리하고 이유를 남기며 작성자에게 알림을 발송합니다.',
        responses={200: OpenApiResponse(description='반려 완료')}
    )
    def post(self, request, pk):
        spec = get_object_or_404(SpecDocument, pk=pk)
        
        status_code = CommonCode.objects.filter(group_id='SPEC_STATUS', code_id='REJECTED').first() \
                      or CommonCode.objects.filter(code_id='PROPOSAL_REJECTED').first()
        if status_code:
            spec.status_code = status_code
            
        spec.reviewer = request.user
        spec.review_comment = request.data.get('reason', spec.review_comment)
        spec.save()
        
        created_by_user = getattr(spec, 'created_by', None) or getattr(spec.meeting, 'created_by', None)
        if created_by_user:
            notify_user(
                created_by_user,
                f"'{spec.title}' 기획서가 반려되었습니다.",
                type='error',
                link='/documents',
            )
        return Response({"message": "기획서가 반려되었습니다.", "spec": SpecDocumentSerializer(spec).data})


class _AudioTranscriptionMixin:
    """음성 -> 텍스트 변환 공용 로직. MeetingNoteTranscribeAudioView(Whisper 받아쓰기)와
    MeetingNoteCleanupTranscriptView(GPT 정리)가 나눠서 쓴다 — 원래 한 번의 API 호출로
    둘 다 처리했는데(2026-09-09), 그러면 프론트가 "지금 받아쓰기 중인지 정리 중인지" 그리고
    "끝나기까지 얼마나 남았는지"를 전혀 알 수 없어 그냥 뭉뚱그린 스피너만 보여줄 수 있었다
    (사용자 요청 — 진행 단계/게이지 표시). 두 단계를 별도 API로 쪼개면 프론트가 각 단계의
    완료 시점을 정확히 알 수 있어 실제 진행률을 보여줄 수 있다."""

    AUDIO_MAX_SIZE = 25 * 1024 * 1024  # 25MB — OpenAI Whisper API 자체 제한과 동일하게 맞춤
    AUDIO_EXTENSIONS = ('.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm')

    @staticmethod
    def _get_openai_client():
        import os
        from openai import OpenAI

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY가 설정되지 않아 음성 변환을 사용할 수 없습니다.")
        return OpenAI(api_key=api_key)

    # 이 팀/프로젝트에서 실제로 자주 나오는 고유명사·기술 용어 — 일반 음성인식 모델이
    # 흔히 놓치거나 다른 단어로 잘못 알아듣는 것들이라, keywords로 미리 힌트를 준다.
    # (실제로 라이브 테스트: keywords 없이는 놓치던 "헤이짜비", "Whisper", "Django",
    # "Next.js" 같은 용어가 keywords를 주자 정확히 인식됨.) 회의 내용에 따라 계속
    # 추가/정리하면 된다 — 너무 길면 오히려 힌트 효과가 흐려지니 실제로 자주 나오는
    # 것 위주로 유지한다.
    TECH_KEYWORDS = [
        "헤이짜비", "HeyZzabi",
        "Django", "Next.js", "React", "TypeScript",
        "Whisper", "GPT", "OpenAI",
        "MySQL", "RDS", "API", "PR",
        "PM", "기획서", "요구사항정의서", "업무배분", "회의록", "스프린트",
    ]

    # keywords는 "이런 단어가 나올 수 있다"는 목록만 주지만, prompt는 자유 문장으로
    # "어떤 자리에서 녹음된 오디오인지" 문맥을 준다 — 두 파라미터는 서로 다른 역할이라
    # 같이 써야 효과가 더 크다(OpenAI 문서 권장 방식). 실제 회의 성격(한국어 위주 +
    # 영어 기술 용어 혼용, IT 개발팀)을 그대로 설명한다.
    TRANSCRIBE_CONTEXT_PROMPT = (
        "이것은 소프트웨어 개발팀의 한국어 회의 녹음입니다. Django, Next.js, React, "
        "TypeScript, Whisper, GPT, MySQL, API 같은 영어 기술 용어와 한국어가 섞여서 "
        "나옵니다. 회의록/기획서/요구사항정의서/업무배분 같은 프로젝트 전용 용어도 "
        "자주 나옵니다."
    )

    @classmethod
    def _transcribe_audio(cls, uploaded_file):
        """OpenAI 음성 받아쓰기. language='ko'로 고정하지 않고 자동 언어 감지에 맡긴다
        — 회의 참석자가 영어 용어를 섞어 쓰는 경우가 흔해서, 언어를 한국어로 강제하면
        오히려 그 구간 인식률이 떨어질 수 있다.

        모델은 whisper-1이 아니라 gpt-transcribe를 쓴다 — OpenAI가 whisper-1의
        후속으로 권장하는 모델이면서 분당 요금이 오히려 더 싸고(2026-09 기준
        whisper-1 $0.006/분 vs gpt-transcribe $0.0045/분), keywords/prompt 파라미터로
        프로젝트 고유명사·기술 용어와 회의 맥락을 미리 힌트로 줄 수 있다(whisper-1에는
        없던 기능). temperature=0은 "그럴듯하게 지어내기"보다 들린 대로 최대한 보수적
        으로 받아쓰게 만든다(창의적 디코딩을 끄는 설정 — 근거 없는 내용을 만들어내면
        안 되는 이 프로젝트의 환각 방지 원칙과 일치).
        실제로 keywords/prompt 없이 "헤이짜비"/"Whisper"/"Django"/"Next.js" 같은
        용어가 틀리게 인식되던 걸 추가 후 라이브로 재현/확인함."""
        client = cls._get_openai_client()
        uploaded_file.seek(0)
        # openai SDK가 Django의 UploadedFile(io.IOBase가 아님)을 그대로는 못 받아들여서
        # (실제로 재현: "Expected entry at `file` to be bytes, an io.IOBase instance,
        # PathLike or a tuple") (파일명, 바이트, content_type) 튜플로 감싸 넘긴다 —
        # 파일명 확장자를 SDK가 보고 포맷을 판단하므로 원본 파일명을 그대로 써야 한다.
        result = client.audio.transcriptions.create(
            model="gpt-transcribe",
            file=(uploaded_file.name, uploaded_file.read(), uploaded_file.content_type or "application/octet-stream"),
            keywords=cls.TECH_KEYWORDS,
            prompt=cls.TRANSCRIBE_CONTEXT_PROMPT,
            temperature=0,
        )
        return result.text

    @classmethod
    def _cleanup_transcript(cls, raw_text: str) -> str:
        """Whisper 받아쓰기 결과는 필러 단어("어", "음", "그니까")가 그대로 남아있고
        문장 구분도 없어서, 회의록 "원본 내용" 칸에 그대로 넣기엔 거칠다 — GPT로 한 번
        다듬어 회의록 형식으로 정리한다. 내용을 창작하거나 요약하지 말고 표현만
        다듬으라고 명시해 AI가 실제로 안 한 말을 지어내는 걸 막는다."""
        if not raw_text or not raw_text.strip():
            return raw_text

        client = cls._get_openai_client()
        # "회의록 형식으로 출력"만 지시하면 GPT가 매번 맨 앞에 "회의록"이라는 제네릭한
        # 제목 줄을 붙인다 — 프론트(NewDocumentModal.deriveTitleFromContent)가 내용의
        # 첫 줄을 문서 제목으로 자동 채우는데, 그러면 음성으로 등록한 문서 제목이 전부
        # "회의록"으로만 채워지는 문제가 있었다(실제로 재현 확인). 제목/일시/참석자 같은
        # 메타 헤더는 붙이지 말고 본문만 정리하라고 명시해서 막는다 — 그 정보는 이미
        # 프론트의 별도 입력칸(문서 제목/회의 일시/참석자)이 담당한다.
        # 받아쓰기 단계(keywords)에서 한 번 걸러졌어도, 발음이 비슷한 기술 용어는
        # 여전히 오인식될 수 있다("장고"처럼 음차되거나 붙여/띄어쓰기가 달라지는 경우
        # 등) — GPT 정리 단계에서 같은 용어집을 다시 참고시켜 2차로 바로잡는다.
        # 용어집에 없는 말을 억지로 끼워 맞추면 안 되므로 "발음이 비슷할 때만"이라고
        # 못박아 환각(없는 내용 추가)을 막는다.
        glossary = ", ".join(cls.TECH_KEYWORDS)
        system_prompt = (
            "너는 회의 음성 받아쓰기 결과를 다듬는 편집자다. 아래 기준을 반드시 지켜라.\n"
            "1. '어', '음', '그니까' 같은 필러 단어를 제거한다.\n"
            "2. 문장 단위로 끊어서 읽기 쉽게 정리한다.\n"
            "3. 내용은 절대 바꾸지 말고 표현만 다듬는다 — 없는 내용을 추가하거나 요약하지 마라.\n"
            "4. '회의록', '일시:', '참석자:' 같은 제목/메타 헤더는 절대 붙이지 마라 — "
            "실제로 말한 본문 내용만 문단이나 번호 목록으로 정리해서 출력한다.\n"
            f"5. 다음은 이 프로젝트에서 실제로 자주 쓰는 용어집이다: {glossary}. "
            "본문에 이 용어들과 발음이 비슷하지만 다르게 표기된 단어(예: 잘못 음차되거나 "
            "띄어쓰기가 달라진 경우)가 있으면 용어집 표기로 바로잡아라. 용어집에 없는 "
            "내용을 새로 추가하거나 억지로 끼워 맞추지는 마라 — 애매하면 원문 그대로 둔다."
        )
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"아래는 음성을 텍스트로 변환한 내용입니다.\n\n{raw_text}"},
            ],
        )
        cleaned = completion.choices[0].message.content
        return cleaned or raw_text


class MeetingNoteTranscribeAudioView(_AudioTranscriptionMixin, APIView):
    """음성 파일 -> 받아쓰기 원문 (1/2단계). 정리 전 원문만 반환 — 정리는
    MeetingNoteCleanupTranscriptView가 이어서 처리한다(프론트 진행률 표시용 분리)."""
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser]

    @extend_schema(
        tags=['1단계 - 회의록'],
        summary='음성 파일 받아쓰기 (1/2단계)',
        description='.mp3/.mp4/.wav/.m4a/.webm 등 음성 파일을 OpenAI Whisper로 받아쓰기해서 원문 텍스트를 돌려준다. DB에 저장하지 않는다.',
        request={'multipart/form-data': {'type': 'object', 'properties': {'file': {'type': 'string', 'format': 'binary'}}}},
        responses={200: OpenApiResponse(description='받아쓰기 원문')},
    )
    def post(self, request):
        f = request.FILES.get('file')
        if not f:
            return Response({"error": "파일이 없습니다."}, status=status.HTTP_400_BAD_REQUEST)
        if not f.name.lower().endswith(self.AUDIO_EXTENSIONS):
            return Response(
                {"error": "지원하지 않는 음성 파일 형식입니다. .mp3, .mp4, .wav, .m4a, .webm 등만 업로드해주세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if f.size > self.AUDIO_MAX_SIZE:
            return Response({"error": "음성 파일 크기는 25MB를 넘을 수 없습니다."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            transcript = self._transcribe_audio(f)
        except RuntimeError as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({"error": f"음성 인식 중 오류가 발생했습니다: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        transcript = (transcript or "").strip()
        if not transcript:
            return Response({"error": "음성에서 텍스트를 인식하지 못했습니다."}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"transcript": transcript}, status=status.HTTP_200_OK)


class MeetingNoteCleanupTranscriptView(_AudioTranscriptionMixin, APIView):
    """받아쓰기 원문 -> 필러 제거·문장 정리 (2/2단계)."""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['1단계 - 회의록'],
        summary='받아쓰기 원문 정리 (2/2단계)',
        description='Whisper 받아쓰기 원문을 GPT로 필러 단어 제거·문장 정리해서 돌려준다. DB에 저장하지 않는다.',
        request={'application/json': {'type': 'object', 'properties': {'text': {'type': 'string'}}}},
        responses={200: OpenApiResponse(description='정리된 텍스트')},
    )
    def post(self, request):
        raw_text = (request.data.get('text') or "").strip()
        if not raw_text:
            return Response({"error": "정리할 텍스트가 없습니다."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            cleaned = self._cleanup_transcript(raw_text)
        except RuntimeError as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({"error": f"내용 정리 중 오류가 발생했습니다: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        cleaned = (cleaned or raw_text).strip()
        return Response({"content": cleaned}, status=status.HTTP_200_OK)


class MeetingNoteParseFileView(APIView):
    """회의록 첨부 문서 파일에서 텍스트 추출 (음성 파일은 MeetingNoteTranscribeAudioView/
    MeetingNoteCleanupTranscriptView 2단계 플로우를 쓴다 — 진행률 표시를 위해 분리됨)"""
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser]

    MAX_SIZE = 10 * 1024 * 1024  # 10MB

    @extend_schema(
        tags=['1단계 - 회의록'],
        summary='회의록 첨부 파일 텍스트 추출',
        description='.docx/.pdf/.txt/.md/.hwp 파일을 업로드하면 텍스트를 추출해서 돌려준다. DB에 저장하지 않는다.',
        request={'multipart/form-data': {'type': 'object', 'properties': {'file': {'type': 'string', 'format': 'binary'}}}},
        responses={200: OpenApiResponse(description='추출된 텍스트')},
    )
    def post(self, request):
        f = request.FILES.get('file')
        if not f:
            return Response({"error": "파일이 없습니다."}, status=status.HTTP_400_BAD_REQUEST)
        if f.size > self.MAX_SIZE:
            return Response({"error": "파일 크기는 10MB를 넘을 수 없습니다."}, status=status.HTTP_400_BAD_REQUEST)

        name = f.name.lower()
        try:
            if name.endswith('.docx'):
                document = docx.Document(f)
                text = self._extract_docx_text(document)
            elif name.endswith('.pdf'):
                reader = PdfReader(f)
                text = "\n".join((page.extract_text() or "") for page in reader.pages)
            elif name.endswith('.txt') or name.endswith('.md'):
                text = f.read().decode('utf-8', errors='ignore')
            elif name.endswith('.hwp'):
                text = self._extract_hwp_text(f)
            else:
                return Response(
                    {"error": "지원하지 않는 파일 형식입니다. .docx, .pdf, .txt, .md, .hwp 파일만 업로드해주세요."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except Exception as e:
            return Response({"error": f"파일을 읽는 중 오류가 발생했습니다: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        text = text.strip()
        if not text:
            return Response({"error": "파일에서 텍스트를 추출하지 못했습니다."}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"content": text, "filename": f.name}, status=status.HTTP_200_OK)

    @staticmethod
    def _extract_docx_text(document):
        lines = []
        for child in document.element.body.iterchildren():
            if child.tag.endswith('}p'):
                text = Paragraph(child, document).text
                if text.strip():
                    lines.append(text)
            elif child.tag.endswith('}tbl'):
                table = Table(child, document)
                rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
                if not rows:
                    continue
                lines.append("| " + " | ".join(rows[0]) + " |")
                lines.append("| " + " | ".join("---" for _ in rows[0]) + " |")
                for row in rows[1:]:
                    lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    @staticmethod
    def _extract_hwp_text(uploaded_file):
        import subprocess
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix='.hwp', delete=False) as tmp:
            for chunk in uploaded_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        try:
            result = subprocess.run(
                ['hwp5txt', tmp_path],
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise ValueError(result.stderr.decode('utf-8', errors='ignore') or "hwp5txt 변환 실패")
            return result.stdout.decode('utf-8', errors='ignore')
        finally:
            os.unlink(tmp_path)
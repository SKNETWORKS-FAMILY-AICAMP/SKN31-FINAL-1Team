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

            sections_map = {}
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


class MeetingNoteParseFileView(APIView):
    """회의록 첨부 파일에서 텍스트 추출"""
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
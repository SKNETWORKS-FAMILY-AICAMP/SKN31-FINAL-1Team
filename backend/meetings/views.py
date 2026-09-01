import json
import re
import html
from django.shortcuts import get_object_or_404
from rest_framework import status, permissions, generics, parsers
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse, OpenApiTypes

import docx

from pypdf import PdfReader

from meetings.models import MeetingNote, SpecDocument
from meetings.serializers import (
    MeetingNoteSerializer,
    MeetingNoteCreateSerializer,
    SpecDocumentSerializer,
)
from common.models import CommonCode
from notifications.services import notify_user, notify_all_pms

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

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save(created_by=request.user)
        
        response_serializer = MeetingNoteSerializer(instance)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class MeetingNoteDetailView(generics.RetrieveUpdateDestroyAPIView):
    """회의록 상세 조회, 수정, 삭제"""
    queryset = MeetingNote.objects.all()
    serializer_class = MeetingNoteSerializer
    permission_classes = [permissions.IsAuthenticated]


# meetings/views.py (MeetingNoteAnalyzeView 클래스 수정)

class MeetingNoteAnalyzeView(APIView):
    """
    회의록 AI 분석 및 기획 초안 자동 생성 API
    POST /api/meetings/notes/{id}/analyze/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        meeting = get_object_or_404(MeetingNote, pk=pk)

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

            # [디버깅] AI가実際に 어떤 Key 형태로 반환하는지 서버 콘솔 출력
            print("=== AI Agent Raw Output Keys ===", plan_dict.keys())
            print("=== AI Agent Data ===", json.dumps(plan_dict, ensure_ascii=False, indent=2))

            # 4. 회의록 상태 업데이트
            summary_val = structured_data.get('summary') if isinstance(structured_data, dict) else None
            meeting.summary_content = summary_val or f"[{meeting.title}] AI 분석이 완료되었습니다."
            meeting.status = MeetingNote.Status.REVIEWED
            meeting.save()

            # AI가 내용을 <p>/<strong>/<ul><li> 같은 HTML 태그를 섞어서 줄 때가 있는데, 화면은
            # 이걸 그냥 일반 텍스트로 보여주므로 태그가 그대로 노출된다(실제로 사용자가 발견한 문제).
            # fe6a95c에서 이 제거 함수 자체가 삭제됐던 걸 복구 — html/re는 여전히 import되어 있다.
            def strip_html_tags(text):
                if not text:
                    return ""
                text_str = str(text)
                decoded_text = html.unescape(text_str)
                clean_text = re.sub(r'<[^>]+>', ' ', decoded_text)
                clean_text = re.sub(r'[ \t]+', ' ', clean_text)
                clean_text = re.sub(r'\n\s*\n', '\n', clean_text)
                return clean_text.strip()

            # 실제 AI 응답 구조 확인 결과(2026-09-01 재확인): 위쪽 레벨에 overview/features 같은
            # 키가 바로 있는 게 아니라, plan_dict["sections"]가 [{key, title, content_html, items}, ...]
            # 형태의 리스트로 온다. 팀원 커밋(fe6a95c)이 이걸 top-level 키 매칭으로 바꿔놓는 바람에
            # 실제로는 전부 매칭 실패 -> "회의에서 논의되지 않았습니다"로만 표시되고 있었다
            # (내용이 있어도 안 보이는데, 폴백 문구가 그럴듯해서 눈치채기 어려웠다).
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

                sections_map[sec_key] = strip_html_tags(content)

            # 기획서 7개 섹션 중 회의에서 실제로 논의 안 된 항목은 AI가 빈 값을 준다 — 화면에
            # 그냥 빈 칸으로 두면 "생성이 덜 됐나?" 오해를 살 수 있어서, 비어있으면 명시적으로
            # "회의에서 논의되지 않았습니다"를 채운다(내용을 지어내지 않는다는 원칙은 그대로 유지).
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

            # 회의록 원문에 "프로젝트 기간: 2026-08-25 ~ 2026-10-24"처럼 명시적인 날짜 범위가
            # 있으면 정규식으로 추출해 자동으로 채운다. 못 찾으면 spec_defaults에 아예 키를 안 넣어서
            # (update_or_create는 defaults에 있는 필드만 덮어쓴다) 이미 사용자가 화면에서 직접
            # 입력해둔 기간이 재생성할 때마다 날아가지 않게 한다.
            period_match = re.search(
                r'(\d{4}-\d{2}-\d{2})\s*(?:~|-|부터)\s*(\d{4}-\d{2}-\d{2})',
                meeting.content or "",
            )
            if period_match:
                spec_defaults['period_start'] = period_match.group(1)
                spec_defaults['period_end'] = period_match.group(2)

            # 6. 기존 기획서가 있다면 필드 값 업데이트 (get_or_create 대신 update_or_create 적용)
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


class SpecDocumentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """기획서 상세 조회, 수정, 삭제"""
    queryset = SpecDocument.objects.all()
    serializer_class = SpecDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]


class SpecDocumentReviewView(APIView):
    """기획서 검토 의견 작성/수정"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        spec = get_object_or_404(SpecDocument, pk=pk)
        review_comment = request.data.get('review_comment', '')
        
        spec.review_comment = review_comment
        spec.reviewer = request.user
        spec.save()
        
        return Response(SpecDocumentSerializer(spec).data, status=status.HTTP_200_OK)


class SpecDocumentSubmitReviewView(APIView):
    """기획서 검토 요청 전송"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        spec = get_object_or_404(SpecDocument, pk=pk)
        status_code = CommonCode.objects.filter(code_id='PROPOSAL_PENDING_REVIEW').first()
        if status_code:
            spec.status_code = status_code
            spec.save()
        notify_all_pms(
            f"'{spec.title}' 기획서 검토요청이 도착했습니다.",
            type='info',
            link='/documents',
        )
        return Response({"message": "검토 요청이 완료되었습니다.", "spec": SpecDocumentSerializer(spec).data})

    patch = post


class SpecDocumentApproveView(APIView):
    """기획서 승인 처리"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        spec = get_object_or_404(SpecDocument, pk=pk)
        status_code = CommonCode.objects.filter(code_id='PROPOSAL_APPROVED').first()
        if status_code:
            spec.status_code = status_code
        spec.reviewer = request.user
        spec.save()
        notify_user(
            spec.meeting.created_by,
            f"'{spec.title}' 기획서가 승인되었습니다.",
            type='success',
            link='/documents',
        )
        return Response({"message": "기획서가 승인되었습니다.", "spec": SpecDocumentSerializer(spec).data})


class SpecDocumentRejectView(APIView):
    """기획서 반려 처리"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        spec = get_object_or_404(SpecDocument, pk=pk)
        status_code = CommonCode.objects.filter(code_id='PROPOSAL_REJECTED').first()
        if status_code:
            spec.status_code = status_code
        spec.reviewer = request.user
        spec.review_comment = request.data.get('reason', spec.review_comment)
        spec.save()
        notify_user(
            spec.meeting.created_by,
            f"'{spec.title}' 기획서가 반려되었습니다.",
            type='error',
            link='/documents',
        )
        return Response({"message": "기획서가 반려되었습니다.", "spec": SpecDocumentSerializer(spec).data})


class MeetingNoteParseFileView(APIView):
    """
    회의록 첨부 파일에서 텍스트를 추출해 반환 (저장은 하지 않음 — 프론트가 "원본 내용" 칸을 채우는 용도)
    POST /api/meetings/notes/parse-file/  (multipart/form-data, key: file)
    지원 형식: .docx, .pdf, .txt, .hwp(HWPv5 바이너리 포맷 — pyhwp의 hwp5txt CLI를 서브프로세스로 호출)
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser]

    MAX_SIZE = 10 * 1024 * 1024  # 10MB — 회의록 텍스트 추출용이라 크게 둘 이유가 없다

    @extend_schema(
        tags=['1단계 - 회의록'],
        summary='회의록 첨부 파일 텍스트 추출',
        description='.docx/.pdf/.txt/.hwp 파일을 업로드하면 텍스트를 추출해서 돌려준다. DB에 저장하지 않는다.',
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
                text = "\n".join(para.text for para in document.paragraphs)
            elif name.endswith('.pdf'):
                reader = PdfReader(f)
                text = "\n".join((page.extract_text() or "") for page in reader.pages)
            elif name.endswith('.txt'):
                text = f.read().decode('utf-8', errors='ignore')
            elif name.endswith('.hwp'):
                text = self._extract_hwp_text(f)
            else:
                return Response(
                    {"error": "지원하지 않는 파일 형식입니다. .docx, .pdf, .txt, .hwp 파일만 업로드해주세요."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except Exception as e:
            return Response({"error": f"파일을 읽는 중 오류가 발생했습니다: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        text = text.strip()
        if not text:
            return Response({"error": "파일에서 텍스트를 추출하지 못했습니다."}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"content": text, "filename": f.name}, status=status.HTTP_200_OK)

    @staticmethod
    def _extract_hwp_text(uploaded_file):
        """
        .hwp(HWPv5)는 바이너리 OLE 복합 문서 포맷이라 python-docx/pypdf 같은 순수 파이썬
        라이브러리로는 못 읽는다 — pyhwp 패키지가 설치하는 hwp5txt CLI를 서브프로세스로
        불러서 변환한다(파이썬 API가 내부 구현 세부사항이라 CLI가 더 안정적).
        """
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
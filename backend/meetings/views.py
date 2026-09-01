# meetings/views.py
import json
import re
import html
from django.shortcuts import get_object_or_404
from rest_framework import status, permissions, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse, OpenApiTypes

from meetings.models import MeetingNote, SpecDocument
from meetings.serializers import (
    MeetingNoteSerializer,
    MeetingNoteCreateSerializer,
    SpecDocumentSerializer,
)
from common.models import CommonCode

# AI 모듈 불러오기
from meeting_analysis.node import run as analyze_meeting
from plan_draft.agent import run as generate_plan


# HTML 태그 및 이스케이프 문자 완전히 제거하는 강화된 헬퍼 함수
def strip_html_tags(text):
    if not text:
        return ""
    
    # 1. 문자열 변환
    text_str = str(text)
    
    # 2. &lt;p&gt; 등의 HTML 엔티티를 <p> 형태의 실제 태그로 디코딩
    decoded_text = html.unescape(text_str)
    
    # 3. <p>, <strong> 등 모든 HTML 태그 제거
    clean_text = re.sub(r'<[^>]+>', ' ', decoded_text)
    
    # 4. 여러 줄 바꿈이나 불필요한 공백 정돈
    clean_text = re.sub(r'[ \t]+', ' ', clean_text)  # 연속된 스페이스/탭 한 개로 줄임
    clean_text = re.sub(r'\n\s*\n', '\n', clean_text)  # 연속된 빈 줄 한 개로 줄임
    
    return clean_text.strip()


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


class MeetingNoteAnalyzeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        meeting = get_object_or_404(MeetingNote, pk=pk)

        meeting.status = MeetingNote.Status.PROCESSING
        meeting.save()

        try:
            analysis_result = analyze_meeting(meeting.content, str(meeting.pk))
            structured_data = analysis_result.data if hasattr(analysis_result, 'data') else analysis_result

            proposal_id = f"PLN-{meeting.pk:03d}"
            doc = generate_plan(structured_data, proposal_id)
            
            if hasattr(doc, 'model_dump'):
                plan_dict = doc.model_dump(mode="json")
            elif hasattr(doc, 'dict'):
                plan_dict = doc.dict()
            elif isinstance(doc, dict):
                plan_dict = doc
            else:
                plan_dict = {}

            # --- 안전한 섹션 파싱 및 HTML 태그 완전히 제거 ---
            sections_map = {}
            if isinstance(plan_dict, dict) and isinstance(plan_dict.get("sections"), list):
                for sec in plan_dict["sections"]:
                    if not isinstance(sec, dict):
                        continue
                    
                    sec_key = sec.get("key")
                    if not sec_key or not isinstance(sec_key, str):
                        continue

                    # 1. content_html 우선 추출
                    content = sec.get("content_html") or ""

                    # 2. content_html이 비어있다면 items 또는 features에서 추출
                    if not content and sec.get("items") and isinstance(sec.get("items"), list):
                        content = "\n".join([f"- {item}" for item in sec["items"] if isinstance(item, (str, int))])
                    
                    if not content and sec.get("features") and isinstance(sec.get("features"), list):
                        lines = []
                        for f in sec["features"]:
                            if isinstance(f, dict):
                                title = f.get('title', '')
                                desc = f.get('description', '')
                                lines.append(f"• {title}: {desc}")
                        content = "\n".join(lines)

                    # 3. 태그 제거 적용
                    cleaned_content = strip_html_tags(content)

                    # 문자열 타입 보장
                    sections_map[sec_key] = cleaned_content

            def safe_get_section(key):
                val = sections_map.get(key, "")
                if isinstance(val, (dict, list)):
                    val = json.dumps(val, ensure_ascii=False)
                return strip_html_tags(val)

            # 회의록 상태 및 요약 저장
            summary_val = structured_data.get('summary') if isinstance(structured_data, dict) else None
            meeting.summary_content = strip_html_tags(summary_val or f"[{meeting.title}] AI 분석이 완료되었습니다.")
            meeting.status = MeetingNote.Status.REVIEWED
            meeting.save()

            # 기획서 생성 및 업데이트
            spec_defaults = {
                'title': f"{meeting.title} - 기획 초안",
                'overview': safe_get_section('overview'),
                'problem_definition': safe_get_section('problem'),
                'target_users': safe_get_section('users'),
                'key_features': safe_get_section('features'),
                'user_scenarios': safe_get_section('scenarios'),
                'tech_stack': safe_get_section('tech_scope'),
                'final_decisions': safe_get_section('decisions'),
            }

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
            import traceback
            print("=== ANALYZE ERROR TRACEBACK ===")
            traceback.print_exc()

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
        status_code = CommonCode.objects.filter(code='REVIEW_SUBMITTED').first()
        if status_code:
            spec.status_code = status_code
            spec.save()
        return Response({"message": "검토 요청이 완료되었습니다.", "spec": SpecDocumentSerializer(spec).data})


class SpecDocumentApproveView(APIView):
    """기획서 승인 처리"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        spec = get_object_or_404(SpecDocument, pk=pk)
        status_code = CommonCode.objects.filter(code='APPROVED').first()
        if status_code:
            spec.status_code = status_code
        spec.reviewer = request.user
        spec.save()
        return Response({"message": "기획서가 승인되었습니다.", "spec": SpecDocumentSerializer(spec).data})


class SpecDocumentRejectView(APIView):
    """기획서 반려 처리"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        spec = get_object_or_404(SpecDocument, pk=pk)
        status_code = CommonCode.objects.filter(code='REJECTED').first()
        if status_code:
            spec.status_code = status_code
        spec.reviewer = request.user
        spec.review_comment = request.data.get('review_comment', spec.review_comment)
        spec.save()
        return Response({"message": "기획서가 반려되었습니다.", "spec": SpecDocumentSerializer(spec).data})
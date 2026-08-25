# config/views.py
from django.shortcuts import render
from django.contrib.auth import get_user_model
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.db import transaction  # 추가

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from meetings.models import MeetingNote
from specs.models import SpecDocument
from tasks.models import TaskAssignment

User = get_user_model()

@ensure_csrf_cookie
def main_outlook(request):
    """테스트용 간단 대시보드 메인 화면"""
    return render(request, 'main_outlook.html')

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def reset_test_data(request):
    try:
        # 1. 회의록 상태를 DRAFT(작성 중)로 초기화해야 검토 테스트 가능!
        MeetingNote.objects.update(status=MeetingNote.Status.DRAFT)
        
        # 2. 기획서 상태 초기화
        SpecDocument.objects.update(status=SpecDocument.Status.GENERATING)
        
        # 3. 업무 배정 내역 삭제
        TaskAssignment.objects.all().delete()
        
        # 4. 사원 is_busy 상태 초기화
        User.objects.update(is_busy=False)
        
        return Response(
            {"message": "테스트 데이터가 성공적으로 초기화되었습니다."},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": "초기화 실패", "detail": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
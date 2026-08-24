# config/views.py
from django.shortcuts import render

def main_outlook(request):
    """테스트용 간단 대시보드 메인 화면"""
    return render(request, 'main_outlook.html')
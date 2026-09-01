# config/urls.py

from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

class DummyNotificationView(APIView):
    def get(self, request):
        # 프론트엔드가 안 깨지도록 빈 알림 목록 반환
        return Response([], status=status.HTTP_200_OK)
    
urlpatterns = [
    path('admin/', admin.site.urls),

    # OpenAPI 3.0 Schema 파일 (JSON/YAML)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    
    # Swagger UI 문서
    path('api/docs/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    
    # Redoc 문서
    path('api/docs/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # 앱별 API 엔드포인트
    path('api/common/', include('common.urls')),
    path('api/users/', include('users.urls')),
    path('api/projects/', include('projects.urls')),
    path('api/meetings/', include('meetings.urls')),
    path('api/requirements/', include('requirements.urls')),
    path('api/tasks/', include('tasks.urls')),
]
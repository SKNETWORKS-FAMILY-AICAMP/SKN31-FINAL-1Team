# config/urls.py

from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

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
    # 2026-09-01: 팀원이 추가했던 DummyNotificationView(빈 배열만 반환)는 urlpatterns에
    # 연결도 안 돼있던 죽은 코드였다 — 실제 알림 앱(notifications)으로 교체.
    path('api/notifications/', include('notifications.urls')),
]

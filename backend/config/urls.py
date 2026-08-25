# config/urls.py
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView, 
    SpectacularRedocView, 
    SpectacularSwaggerView
)
from config.views import main_outlook, reset_test_data

urlpatterns = [
    # 1. Django Admin
    path('admin/', admin.site.urls),
    
    # API 라우터 포함
    path('api/v1/', include('users.urls')),
    path('api/v1/', include('meetings.urls')),
    path('api/v1/', include('specs.urls')),
    path('api/v1/', include('tasks.urls')),
    
    # 4. OpenAPI 및 Swagger 문서 UI
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/v1/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/v1/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
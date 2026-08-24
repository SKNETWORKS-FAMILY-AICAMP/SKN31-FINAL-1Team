# config/urls.py
"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView, 
    SpectacularRedocView, 
    SpectacularSwaggerView
)
from config.views import main_outlook

urlpatterns = [
    path('admin/', admin.site.urls),
    path('test-dashboard/', main_outlook, name='main-outlook'), # 웹 테스트 화면 URL
    
    # API 라우터 포함
    path('api/v1/', include('meetings.urls')),
    path('api/v1/', include('specs.urls')),
    path('api/v1/', include('tasks.urls')),
    
    # OpenAPI 스키마 파일 (json/yaml)
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    
    # Swagger UI
    path('api/v1/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    
    # ReDoc UI (선택 사항)
    path('api/v1/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
# users/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserViewSet, CustomTokenObtainPairView, CustomTokenRefreshView

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')

urlpatterns = [
    # 기존 SimpleJWT 뷰 대신 커스텀 뷰로 연결
    path('users/login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('users/refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),
    
    path('', include(router.urls)),
]
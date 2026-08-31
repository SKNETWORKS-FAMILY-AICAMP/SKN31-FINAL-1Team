from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    LoginView,
    LogoutView,
    CurrentUserProfileView,
    UserListView,
    UserManageView,
    UserPasswordResetView,
    UserImpersonateView,
)

urlpatterns = [
    path('me/', CurrentUserProfileView.as_view(), name='user-me'),
    path('', UserListView.as_view(), name='user-list'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    # simplejwt가 기본 제공하는 뷰 — {refresh: "..."}를 보내면 새 access 토큰을 발급한다.
    # access 토큰 기본 수명이 5분(SIMPLE_JWT 설정 없음 = 라이브러리 기본값)이라, 이게 없으면
    # 로그인하고 5분마다 모든 API가 401을 받고 강제 로그아웃됐다(실제로 겪은 문제).
    path('token-refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('<int:pk>/', UserManageView.as_view(), name='user-manage'),
    path('<int:id>/password-reset/', UserPasswordResetView.as_view(), name='user-password-reset'),
    path('<int:id>/impersonate/', UserImpersonateView.as_view(), name='user-impersonate'),
]
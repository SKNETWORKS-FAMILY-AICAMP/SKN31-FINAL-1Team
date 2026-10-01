#users/urls.py
from django.urls import path
from .views import (
    CsrfCookieView,
    UploadTokenView,
    LoginView,
    LogoutView,
    CookieTokenRefreshView,
    CurrentUserProfileView,
    ChangePasswordView,
    UserListView,
    UserManageView,
    UserPasswordResetView,
    UserImpersonateView,
    UserStopImpersonateView,
    MySkillListCreateView,
    MySkillDetailView,
    MyCertificationListCreateView,
    MyCertificationDetailView,
)

urlpatterns = [
    path('me/', CurrentUserProfileView.as_view(), name='user-me'),
    path('me/change-password/', ChangePasswordView.as_view(), name='user-change-password'),
    path('me/skills/', MySkillListCreateView.as_view(), name='my-skills'),
    path('me/skills/<int:pk>/', MySkillDetailView.as_view(), name='my-skill-detail'),
    path('me/certifications/', MyCertificationListCreateView.as_view(), name='my-certifications'),
    path('me/certifications/<int:pk>/', MyCertificationDetailView.as_view(), name='my-certification-detail'),
    path('', UserListView.as_view(), name='user-list'),
    path('csrf/', CsrfCookieView.as_view(), name='csrf-cookie'),
    path('upload-token/', UploadTokenView.as_view(), name='upload-token'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    # 2026-08-31: 토큰을 HttpOnly 쿠키로 옮기면서 simplejwt 기본 TokenRefreshView(요청 바디로
    # refresh 토큰을 받는 방식) 대신, 쿠키에서 직접 읽는 커스텀 뷰로 교체했다.
    path('token-refresh/', CookieTokenRefreshView.as_view(), name='token-refresh'),
    path('dev-stop-impersonate/', UserStopImpersonateView.as_view(), name='user-stop-impersonate'),
    path('<int:pk>/', UserManageView.as_view(), name='user-manage'),
    path('<int:id>/password-reset/', UserPasswordResetView.as_view(), name='user-password-reset'),
    path('<int:id>/impersonate/', UserImpersonateView.as_view(), name='user-impersonate'),
]

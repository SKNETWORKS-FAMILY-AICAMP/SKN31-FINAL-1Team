from django.urls import path
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
    path('<int:pk>/', UserManageView.as_view(), name='user-manage'),
    path('<int:id>/password-reset/', UserPasswordResetView.as_view(), name='user-password-reset'),
    path('<int:id>/impersonate/', UserImpersonateView.as_view(), name='user-impersonate'),
]
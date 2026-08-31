from django.urls import path
from .views import LoginView, LogoutView, CurrentUserProfileView, UserListView

urlpatterns = [
    path('me/', CurrentUserProfileView.as_view(), name='user-me'),
    path('', UserListView.as_view(), name='user-list'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
]
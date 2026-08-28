from django.urls import path
from users.views import CurrentUserProfileView, UserListView

urlpatterns = [
    path('me/', CurrentUserProfileView.as_view(), name='user-me'),
    path('', UserListView.as_view(), name='user-list'),
]
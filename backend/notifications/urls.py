#notifications/urls.py
from django.urls import path
from notifications.views import (
    NotificationListView,
    NotificationMarkReadView,
    NotificationMarkAllReadView,
)

urlpatterns = [
    path('', NotificationListView.as_view(), name='notification-list'),
    path('read-all/', NotificationMarkAllReadView.as_view(), name='notification-mark-all-read'),
    path('<int:pk>/read/', NotificationMarkReadView.as_view(), name='notification-mark-read'),
]

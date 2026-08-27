from django.urls import path
from tasks.views import (
    TaskAssignmentListCreateView,
    TaskAssignmentDetailView,
    AutoTaskAssignView,
    TaskStatusUpdateView,
)

urlpatterns = [
    path('assignments/', TaskAssignmentListCreateView.as_view(), name='task-list'),
    path('assignments/<int:pk>/', TaskAssignmentDetailView.as_view(), name='task-detail'),
    path('auto-assign/', AutoTaskAssignView.as_view(), name='task-auto-assign'),
    path('assignments/<int:pk>/status/', TaskStatusUpdateView.as_view(), name='task-status-update'),
]
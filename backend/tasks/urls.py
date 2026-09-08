# tasks/urls.py
from django.urls import path
from tasks.views import (
    TaskAssignmentListCreateView,
    TaskAssignmentDetailView,
    AutoTaskAssignView,
    TaskStatusUpdateView,
    AIAssigneeMappingView,
    AITaskGenerationView,
)

urlpatterns = [
    path('assignments/', TaskAssignmentListCreateView.as_view(), name='task-list'),
    path('assignments/<int:pk>/', TaskAssignmentDetailView.as_view(), name='task-detail'),
    path('auto-assign/', AutoTaskAssignView.as_view(), name='task-auto-assign'),
    path('assignments/<int:pk>/status/', TaskStatusUpdateView.as_view(), name='task-status-update'),
    
    # AI 관련 엔드포인트 추가
    path('ai/assignee-mapping/', AIAssigneeMappingView.as_view(), name='ai-assignee-mapping'),
    path('ai/task-generation/', AITaskGenerationView.as_view(), name='ai-task-generation'),
]
from django.urls import path
from projects.views import (
    ProjectListCreateView,
    ProjectDetailView,
    PipelineHistoryListView,
)

urlpatterns = [
    path('', ProjectListCreateView.as_view(), name='project-list'),
    path('<int:pk>/', ProjectDetailView.as_view(), name='project-detail'),
    path('<int:project_id>/history/', PipelineHistoryListView.as_view(), name='project-history'),
]
from django.urls import path
from projects.views import (
    ProjectListCreateView,
    ProjectDetailView,
    PipelineHistoryListView,
)

urlpatterns = [
    path('', ProjectListCreateView.as_view(), name='project-list'),
    # 히스토리 탭 프로젝트 필터(전체 보기) — project_id 없이 호출하면 전체 프로젝트를
    # 합쳐서 반환한다. <int:pk>/ 보다 먼저 둬야 하는 건 아니지만("history"는 int가
    # 아니라 애초에 겹치지 않음) 명시적 리터럴 경로를 동적 경로보다 위에 두는 관례를 따른다.
    path('history/', PipelineHistoryListView.as_view(), name='all-history'),
    path('<int:pk>/', ProjectDetailView.as_view(), name='project-detail'),
    path('<int:project_id>/history/', PipelineHistoryListView.as_view(), name='project-history'),
]
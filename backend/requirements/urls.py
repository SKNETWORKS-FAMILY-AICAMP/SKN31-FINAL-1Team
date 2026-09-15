#requirements/urls.py
from django.urls import path
from requirements.views import (
    RequirementDefinitionListCreateView,
    RequirementDefinitionDetailView,
    RequirementDefinitionSubmitReviewView,
    RequirementDefinitionApproveView,
    RequirementDefinitionRejectView,
    RequirementExtractView,
    RequirementExtractionJobStatusView,
    RequirementGenerateTasksView,
    RequirementGenerateTasksJobStatusView,
    RequirementConfirmTasksView,
    RequirementItemViewSet,
    RequirementItemDetailView,
)

urlpatterns = [
    path('', RequirementDefinitionListCreateView.as_view(), name='requirement-list'),
    path('<int:spec_id>/', RequirementDefinitionDetailView.as_view(), name='requirement-detail'),
    
    # 검토 요청 / 승인 / 반려 경로 추가
    path('<int:spec_id>/submit-review/', RequirementDefinitionSubmitReviewView.as_view(), name='requirement-submit-review'),
    path('<int:spec_id>/approve/', RequirementDefinitionApproveView.as_view(), name='requirement-approve'),
    path('<int:spec_id>/reject/', RequirementDefinitionRejectView.as_view(), name='requirement-reject'),
    
    path('<int:spec_id>/extract/', RequirementExtractView.as_view(), name='requirement-extract'),
    path('extraction-jobs/<uuid:job_id>/', RequirementExtractionJobStatusView.as_view(), name='requirement-extraction-job-status'),
    path('<int:spec_id>/generate-tasks/', RequirementGenerateTasksView.as_view(), name='requirement-generate-tasks'),
    path('generate-tasks-jobs/<uuid:job_id>/', RequirementGenerateTasksJobStatusView.as_view(), name='requirement-generate-tasks-job-status'),
    path('<int:spec_id>/confirm-tasks/', RequirementConfirmTasksView.as_view(), name='requirement-confirm-tasks'),
    path('items/', RequirementItemViewSet.as_view(), name='requirement-item-list'),
    path('items/<int:pk>/', RequirementItemDetailView.as_view(), name='item-detail'),  # PATCH, DELETE 지원
]
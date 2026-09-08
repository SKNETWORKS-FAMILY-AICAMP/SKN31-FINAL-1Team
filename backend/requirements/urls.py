from django.urls import path
from requirements.views import (
    RequirementDefinitionListCreateView,
    RequirementDefinitionDetailView,
    RequirementExtractView,
    RequirementItemViewSet,
    RequirementItemDetailView,
)

urlpatterns = [
    path('', RequirementDefinitionListCreateView.as_view(), name='requirement-list'),
    path('<int:spec_id>/', RequirementDefinitionDetailView.as_view(), name='requirement-detail'),
    path('<int:spec_id>/extract/', RequirementExtractView.as_view(), name='requirement-extract'),
    path('items/', RequirementItemViewSet.as_view(), name='requirement-item-list'),
    path('items/', RequirementItemViewSet.as_view(), name='item-list-create'),
    path('items/<int:pk>/', RequirementItemDetailView.as_view(), name='item-detail'),  # PATCH, DELETE 지원
]
from django.urls import path
from requirements.views import (
    RequirementDefinitionListCreateView,
    RequirementDefinitionDetailView,
    RequirementExtractView,
    RequirementItemViewSet,
)

urlpatterns = [
    path('', RequirementDefinitionListCreateView.as_view(), name='requirement-list'),
    path('<int:pk>/', RequirementDefinitionDetailView.as_view(), name='requirement-detail'),
    path('<int:pk>/extract/', RequirementExtractView.as_view(), name='requirement-extract'),
    path('items/', RequirementItemViewSet.as_view(), name='requirement-item-list'),
]
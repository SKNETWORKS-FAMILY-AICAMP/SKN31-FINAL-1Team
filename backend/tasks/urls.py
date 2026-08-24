from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TaskAssignmentViewSet

router = DefaultRouter()
router.register(r'tasks', TaskAssignmentViewSet, basename='task')

urlpatterns = [
    path('', include(router.urls)),
]
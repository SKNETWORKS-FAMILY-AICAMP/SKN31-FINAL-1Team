from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SpecDocumentViewSet

router = DefaultRouter()
router.register(r'specs', SpecDocumentViewSet, basename='spec')

urlpatterns = [
    path('', include(router.urls)),
]
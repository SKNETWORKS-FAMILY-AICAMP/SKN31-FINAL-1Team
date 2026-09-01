from django.urls import path
from meetings.views import (
    MeetingNoteListCreateView,
    MeetingNoteDetailView,
    MeetingNoteAnalyzeView,
    SpecDocumentListCreateView,
    SpecDocumentDetailView,
    SpecDocumentReviewView,
    SpecDocumentSubmitReviewView,
    SpecDocumentApproveView,
    SpecDocumentRejectView,
)

urlpatterns = [
    # 회의록 엔드포인트
    path('notes/', MeetingNoteListCreateView.as_view(), name='meeting-note-list'),
    path('notes/<int:pk>/', MeetingNoteDetailView.as_view(), name='meeting-note-detail'),
    path('notes/<int:pk>/analyze/', MeetingNoteAnalyzeView.as_view(), name='meeting-note-analyze'),

    # 기획서 엔드포인트
    path('specs/', SpecDocumentListCreateView.as_view(), name='spec-document-list'),
    path('specs/<int:pk>/', SpecDocumentDetailView.as_view(), name='spec-document-detail'),
    path('specs/<int:pk>/review/', SpecDocumentReviewView.as_view(), name='spec-document-review'),
    path('specs/<int:pk>/submit-review/', SpecDocumentSubmitReviewView.as_view(), name='spec-document-submit-review'),
    path('specs/<int:pk>/approve/', SpecDocumentApproveView.as_view(), name='spec-document-approve'),
    path('specs/<int:pk>/reject/', SpecDocumentRejectView.as_view(), name='spec-document-reject'),
]
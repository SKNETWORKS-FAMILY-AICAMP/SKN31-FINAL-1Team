#meetings/models.py
from django.db import models
from django.conf import settings
from common.models import CommonCode


class MeetingNote(models.Model):
    """
    1단계 - 회의록 (meeting_note)
    """
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', '작성 중'
        PROCESSING = 'PROCESSING', 'AI 분석 중'
        REVIEWED = 'REVIEWED', '검토 완료'

    meeting_id = models.AutoField(primary_key=True, verbose_name="회의록 ID")
    title = models.CharField(max_length=200, verbose_name="회의 제목")
    content = models.TextField(verbose_name="회의록 원문/내용")
    summary_content = models.TextField(null=True, blank=True, verbose_name="AI 핵심 요약")
    
    meeting_date = models.DateTimeField(null=True, blank=True, verbose_name="회의 일시")
    attendees = models.TextField(null=True, blank=True, verbose_name="참석자 목록")
    status = models.CharField(
        max_length=20, 
        choices=Status.choices, 
        default=Status.DRAFT, 
        verbose_name="상태"
    )
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="meeting_notes", 
        verbose_name="작성자"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성 일시")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정 일시")

    class Meta:
        db_table = "meeting_note"
        verbose_name = "회의록"
        verbose_name_plural = "회의록 목록"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.meeting_id}] {self.title}"


class SpecDocument(models.Model):
    """
    1-2단계 - 기획서 / 초안 (spec_document / proposal)
    회의록을 바탕으로 생성되는 기획서
    """
    spec_id = models.AutoField(primary_key=True, verbose_name="기획서 ID")
    meeting = models.ForeignKey(
        MeetingNote,
        on_delete=models.CASCADE,
        related_name="spec_documents",
        db_column="meeting_id",
        verbose_name="관련 회의록"
    )
    
    title = models.CharField(max_length=200, verbose_name="기획서 제목")
    overview = models.TextField(null=True, blank=True, verbose_name="프로젝트 개요")
    background = models.TextField(null=True, blank=True, verbose_name="추진 배경")
    target_scope = models.TextField(null=True, blank=True, verbose_name="개발 및 추진 범위")
    key_features = models.TextField(null=True, blank=True, verbose_name="주요 기능 요약")
    
    status_code = models.ForeignKey(
        CommonCode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="spec_status",
        db_column="status_code",
        verbose_name="검토 상태"
    )
    
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_specs",
        db_column="reviewer_id",
        verbose_name="검토자"
    )
    review_comment = models.TextField(null=True, blank=True, verbose_name="검토 의견")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성 일시")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정 일시")

    class Meta:
        db_table = "spec_document"
        verbose_name = "기획서"
        verbose_name_plural = "기획서 목록"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.spec_id}] {self.title}"
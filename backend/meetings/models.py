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

    # 2026-08-31: documents 화면을 Django 기준으로 재배선하면서 추가. 회의록이 어느 프로젝트
    # 소속인지 알 방법이 전혀 없어서(PipelineHistory.project가 필수인데 연결할 방법이 없었음)
    # 프론트의 "프로젝트별 문서 목록" 화면을 그대로 옮길 수가 없었다 — null 허용은 기존 데이터 호환용.
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meeting_notes",
        verbose_name="소속 프로젝트"
    )

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

    # 2026-08-31: 기획서 화면을 "1.프로젝트개요~7.최종결정사항" 7개 섹션으로 재설계하면서 추가.
    # 팀 결정: 7개 섹션 전부 자유 텍스트(한 덩어리)로 관리 — 4/5/7번(주요기능/시나리오/결정사항)도
    # 카드·리스트로 행 단위 저장하지 않고 줄바꿈으로 구분된 하나의 텍스트로 둔다.
    overview = models.TextField(null=True, blank=True, verbose_name="1. 프로젝트 개요")
    problem_definition = models.TextField(null=True, blank=True, verbose_name="2. 문제 정의")
    target_users = models.TextField(null=True, blank=True, verbose_name="3. 대상 사용자")
    key_features = models.TextField(null=True, blank=True, verbose_name="4. 주요 기능")
    user_scenarios = models.TextField(null=True, blank=True, verbose_name="5. 사용자 시나리오")
    tech_stack = models.TextField(null=True, blank=True, verbose_name="6. 기술 스택 및 제약사항")
    final_decisions = models.TextField(null=True, blank=True, verbose_name="7. 최종 결정사항")

    # background/target_scope: 이 7섹션 템플릿 이전에 쓰이던 필드 — 새 화면에서는 안 쓰지만
    # 기존 데이터 호환을 위해 그대로 남겨둔다.
    background = models.TextField(null=True, blank=True, verbose_name="추진 배경 (구 필드, 미사용)")
    target_scope = models.TextField(null=True, blank=True, verbose_name="개발 및 추진 범위 (구 필드, 미사용)")

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
from django.db import models
from django.conf import settings


class Project(models.Model):
    """
    프로젝트 기본 정보 (project)
    """
    name = models.CharField(max_length=200, verbose_name="프로젝트명")
    description = models.TextField(null=True, blank=True, verbose_name="프로젝트 설명")
    
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_projects",
        verbose_name="프로젝트 관리자"
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성 일시")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정 일시")

    class Meta:
        db_table = "project"
        verbose_name = "프로젝트"
        verbose_name_plural = "프로젝트 목록"

    def __str__(self):
        return f"[{self.id}] {self.name}"


class PipelineHistory(models.Model):
    """
    파이프라인 전체 이력 로그 (pipeline_history)
    (회의록 -> 기획서 -> 요구사항 -> 업무 배정까지의 전체 타임라인)
    """
    STEP_CHOICES = (
        ('MEETING_REGISTERED', '회의록 등록'),
        ('SPEC_GENERATED', '기획서 생성/검토'),
        ('REQ_DEFINED', '요구사항정의서 확정'),
        ('TASK_ASSIGNED', '업무 자동 배정'),
        ('TASK_IN_PROGRESS', '업무 진행 중'),
        ('COMPLETED', '파이프라인 완료'),
    )

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="histories",
        verbose_name="프로젝트"
    )
    
    # 각 단계별 산출물 연동 (단계 진행에 따라 FK 연결)
    meeting = models.ForeignKey(
        'meetings.MeetingNote', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        verbose_name="관련 회의록"
    )
    spec = models.ForeignKey(
        'meetings.SpecDocument', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        verbose_name="관련 기획서"
    )
    requirement = models.ForeignKey(
        'requirements.RequirementDefinition', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        verbose_name="관련 요구사항정의서"
    )
    task = models.ForeignKey(
        'tasks.TaskAssignment', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        verbose_name="관련 업무"
    )
    
    step_type = models.CharField(max_length=30, choices=STEP_CHOICES, verbose_name="파이프라인 단계")
    title = models.CharField(max_length=200, verbose_name="이력 요약 타이틀")
    description = models.TextField(null=True, blank=True, verbose_name="상세 변경 내용/로그")
    
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="작업자/진행자"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="발생 일시")

    class Meta:
        db_table = "pipeline_history"
        verbose_name = "파이프라인 이력"
        verbose_name_plural = "파이프라인 이력 목록"
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.project.name}] {self.get_step_type_display()} - {self.title}"
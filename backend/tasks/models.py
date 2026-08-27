from django.db import models
from django.conf import settings
from common.models import CommonCode


class TaskAssignment(models.Model):
    """
    3단계 - 배정된 업무 (task_assignment)
    요구사항 항목(RequirementItem)을 바탕으로 담당자에게 자동 배정 및 승인 관리
    """
    class Status(models.TextChoices):
        PENDING_APPROVAL = 'PENDING_APPROVAL', '승인 대기'
        APPROVED = 'APPROVED', '승인 및 알림 완료'
        IN_PROGRESS = 'IN_PROGRESS', '진행 중'
        COMPLETED = 'COMPLETED', '완료'

    # 요구사항 항목 참조 (기존 specs.SpecDocument -> requirements.RequirementItem으로 변경)
    req_item = models.ForeignKey(
        'requirements.RequirementItem',
        on_delete=models.CASCADE,
        related_name='assignments',
        verbose_name="관련 요구사항 항목"
    )
    
    # 담당자 (기존 assigned_user 필드 유지)
    assigned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tasks',
        verbose_name="담당자"
    )
    
    # 업무 정보 (기존 task_title, task_description 필드 유지)
    task_title = models.CharField(max_length=200, verbose_name="업무 제목")
    task_description = models.TextField(verbose_name="업무 상세 내용")
    
    status = models.CharField(
        max_length=20, 
        choices=Status.choices, 
        default=Status.PENDING_APPROVAL,
        verbose_name="진행/승인 상태"
    )
    
    # 일정 정보
    start_date = models.DateField(null=True, blank=True, verbose_name="시작 예정일")
    due_date = models.DateField(null=True, blank=True, verbose_name="마감 예정일")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성 일시")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정 일시")

    class Meta:
        db_table = "task_assignment"
        verbose_name = "배정 업무"
        verbose_name_plural = "배정 업무 목록"
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.id}] {self.task_title} ({self.get_status_display()})"
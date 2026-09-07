from django.db import models
from django.conf import settings
from common.models import CommonCode


class TaskStatusCode:
    """
    task_assignment.status_code 에 들어갈 common_code.code_id 상수.
    common_code 테이블에 group_code='TASK_STATUS' 로 아래 code_id 들이 시드되어 있어야 한다.
    (기존 TaskAssignment.Status TextChoices 를 CommonCode 로 이관하면서 도입)
    """
    PENDING_APPROVAL = 'PENDING_APPROVAL'
    APPROVED = 'APPROVED'
    REJECTED = 'REJECTED'
    IN_PROGRESS = 'IN_PROGRESS'
    COMPLETED = 'COMPLETED'
    VALUES = {PENDING_APPROVAL, APPROVED, REJECTED, IN_PROGRESS, COMPLETED}


class TaskAssignment(models.Model):
    """
    3단계 - 배정된 업무 (task_assignment)
    요구사항 항목(RequirementItem)을 바탕으로 담당자에게 배정.

    2026-09-07: 컬럼 전면 재설계 ("TASK 수정.xlsx" 명세 기준).
      - task_title/task_description/status(TextChoices)/due_date 제거
      - title/description/end_date 로 대체, 상태는 status_code(CommonCode FK)로 이관
      - Git 연동(linked_*), 에픽/부모 업무, 배정 근거·부하율·예상 공수 필드 신설
    """

    # ── 식별 ────────────────────────────────────────────
    task_no = models.CharField(
        max_length=20, unique=True, null=True, blank=True,
        verbose_name="업무배분 번호 (예: TASK-001)",
    )

    # ── 관계 ────────────────────────────────────────────
    req_item = models.ForeignKey(
        'requirements.RequirementItem',
        on_delete=models.CASCADE,
        related_name='assignments',
        verbose_name="관련 요구사항 항목",
    )
    assigned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tasks',
        verbose_name="담당자",
    )
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='task_assignments',
        verbose_name="프로젝트",
    )

    # ── 업무 내용 ───────────────────────────────────────
    title = models.CharField(max_length=200, default="", verbose_name="업무명")
    description = models.TextField(null=True, blank=True, verbose_name="업무 상세 설명")
    difficulty_reason = models.TextField(null=True, blank=True, verbose_name="난이도 판단 근거")
    estimated_hours = models.FloatField(null=True, blank=True, verbose_name="예상 소요 시간")
    assignment_reason = models.TextField(null=True, blank=True, verbose_name="배정 근거")
    assigned_workload = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name="배정 시점 부하율",
    )
    reject_reason = models.CharField(max_length=500, null=True, blank=True, verbose_name="반려 사유")

    # ── 일정 / 진행 ─────────────────────────────────────
    start_date = models.DateField(null=True, blank=True, verbose_name="시작일")
    end_date = models.DateField(null=True, blank=True, verbose_name="종료 예정일")
    progress = models.IntegerField(default=0, verbose_name="진행률(%)")

    # ── Git 연동 ────────────────────────────────────────
    linked_branch = models.CharField(max_length=200, null=True, blank=True, verbose_name="연결 브랜치명")
    linked_pr_number = models.IntegerField(null=True, blank=True, verbose_name="연결 PR 번호")
    linked_pr_url = models.CharField(max_length=300, null=True, blank=True, verbose_name="연결 PR 링크")

    # ── 코드값 (common_code) ────────────────────────────
    status_code = models.ForeignKey(
        CommonCode, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='task_status', db_column='status_code',
        verbose_name="업무 상태 코드",
    )
    difficulty_code = models.ForeignKey(
        CommonCode, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='task_difficulty', db_column='difficulty_code',
        verbose_name="난이도 코드",
    )
    git_status_code = models.ForeignKey(
        CommonCode, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='task_git_status', db_column='git_status_code',
        verbose_name="Git 연동 상태 코드",
    )

    # ── 계층 / 에픽 ─────────────────────────────────────
    # 부모 업무의 task_no 를 문자열로 저장 (FK 아님). 컬럼명은 명세서대로 parent_task_id.
    parent_task = models.CharField(
        max_length=20, null=True, blank=True,
        db_column="parent_task_id", verbose_name="부모 업무 번호",
    )
    epic_no = models.CharField(max_length=20, default="", verbose_name="epic ID")
    epic_title = models.CharField(max_length=200, default="", verbose_name="epic 제목")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성 일시")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정 일시")

    class Meta:
        db_table = "task_assignment"
        verbose_name = "배정 업무"
        verbose_name_plural = "배정 업무 목록"
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.task_no or self.id}] {self.title}"

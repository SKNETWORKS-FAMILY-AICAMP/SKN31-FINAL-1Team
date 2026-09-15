#tasks/models.py
import uuid

from django.db import models
from django.conf import settings
from common.models import CommonCode


class TaskStatusCode:
    """
    task_assignment.status_code 에 들어갈 common_code.code_id 상수.
    common_code 테이블에 group_code='TASK_STATUS' 로 아래 code_id 들이 시드되어 있어야 한다.
    (기존 TaskAssignment.Status TextChoices 를 CommonCode 로 이관하면서 도입)

    2026-09-15 수정 — common_code.code_id는 테이블 전체에서 전역으로 유일한 PK라
    그룹마다 같은 문자열을 다시 쓸 수 없다(common/models.py CommonCode 참고). 원래
    여기 있던 APPROVED/REJECTED/COMPLETED는 TASK_STATUS로 시드된 적이 없고, 실제로는
    이미 다른 그룹이 선점한 code_id였다(라이브 DB로 실측 확인):
      - APPROVED  -> REQSPEC_STATUS("승인완료")
      - REJECTED  -> REQSPEC_STATUS("반려")
      - COMPLETED -> PROJECT_STATUS("완료")
    FK가 그룹을 검증하지 않아 에러 없이 조용히 엉뚱한 그룹의 행을 가리켜왔다(예:
    대시보드의 완료 업무 집계가 TaskStatusCode.COMPLETED로 필터링해 항상 0건이었음).

    REJECTED는 TASK_STATUS에 이미 있는 CANCELLED를 재사용한다(팀 결정) — 프론트가
    둘을 구분해서 쓰는 곳이 없어(taskOverdue.ts는 DONE/CANCELLED/COMPLETED/REJECTED를
    어차피 동일하게 "종료됨"으로 취급) 충돌이 없다.

    APPROVED는 한때 COMPLETED(DONE)와 합쳤었는데(2026-09-15), 프론트
    (projects/[id]/page.tsx, tasks/page.tsx, KanbanBoard.tsx)가 "승인됨"을
    "완료"와 다른 색·다른 칸반 단계로 이미 설계해둔 게 뒤늦게 확인돼 되돌렸다 —
    TASK_STATUS 전용 code_id(TASK_APPROVED)를 새로 시드했다
    (common/migrations/0002_add_task_status_approved.py). 업무 배분이 막
    확정된 시점의 초기 상태는 APPROVED가 아니라 PENDING_APPROVAL이다(PM이 개별
    업무를 나중에 승인/반려하는 것과, 배분 자체를 확정하는 것은 서로 다른 액션 —
    confirm_task_assignments 참고).

    2026-09-15 (임시저장): AI가 "업무 배분 실행" 직후 만드는 초안도 이제 즉시
    TaskAssignment로 저장한다(그래야 PM이 며칠 뒤 돌아와도 안 날아감) — 이때는
    아직 아무도 검토 전이라 PENDING_APPROVAL과는 구분해야 한다. 새 code_id를
    또 만들지 않고 TASK_STATUS에 이미 있지만 아무 데도 안 쓰이던 BACKLOG("대기")를
    "AI 초안, 검토 전" 의미로 재사용한다 — PM이 확정하면 PENDING_APPROVAL로 전환.
    """
    BACKLOG = 'BACKLOG'
    PENDING_APPROVAL = 'PENDING_APPROVAL'
    APPROVED = 'TASK_APPROVED'
    REJECTED = 'CANCELLED'
    IN_PROGRESS = 'IN_PROGRESS'
    COMPLETED = 'DONE'
    VALUES = {BACKLOG, PENDING_APPROVAL, APPROVED, REJECTED, IN_PROGRESS, COMPLETED}

#tasks/models.py
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


class TaskGenerationJob(models.Model):
    """
    "업무 배분 실행"이 순차 LLM 호출 여러 개(1~수 분)라 동기 요청으로 두면 PM이
    화면을 몇 분씩 붙잡고 있어야 하는 문제(2026-09-14 확인)를 개선하기 위해
    도입 — 버튼을 누르면 백그라운드 스레드로 파이프라인을 돌리고, 이 테이블에
    진행 단계를 기록해 프론트가 폴링으로 진행 상태를 보여준다.

    Celery/Redis 같은 별도 워커 인프라가 아직 이 프로젝트에 없어(2026-09-14
    확인 — requirements.txt에만 있고 실제 설정은 없음) threading.Thread로
    가볍게 구현했다. 개발 서버(단일 프로세스)에서는 문제없지만, 운영에서
    gunicorn 워커가 여러 개거나 배포 중 워커가 재시작되면 실행 중이던 스레드가
    통째로 유실될 수 있다 — 이 한계를 감수한 임시 구현이며, 나중에 워커 큐를
    실제로 두게 되면 이 모델의 상태 필드만 그대로 재사용하고 실행 방식만
    바꾸면 된다.
    """
    STATUS_PENDING = "PENDING"
    STATUS_RUNNING = "RUNNING"
    STATUS_SUCCESS = "SUCCESS"
    STATUS_ERROR = "ERROR"
    STATUS_CHOICES = [
        (STATUS_PENDING, "대기"),
        (STATUS_RUNNING, "진행 중"),
        (STATUS_SUCCESS, "완료"),
        (STATUS_ERROR, "실패"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    spec = models.ForeignKey(
        'meetings.SpecDocument', on_delete=models.CASCADE,
        related_name='task_generation_jobs', verbose_name="대상 기획서",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='task_generation_jobs', verbose_name="실행자",
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING, verbose_name="상태")
    stage = models.CharField(max_length=100, default="", blank=True, verbose_name="현재 진행 단계(사람이 읽는 라벨)")
    result = models.JSONField(null=True, blank=True, verbose_name="성공 시 결과(generate_task_suggestions 반환값)")
    error_message = models.TextField(null=True, blank=True, verbose_name="실패 시 오류 메시지")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "task_generation_job"
        verbose_name = "업무 배분 실행 작업"
        verbose_name_plural = "업무 배분 실행 작업 목록"
        ordering = ['-created_at']


class EmployeeExperienceTagCache(models.Model):
    """
    User.past_projects(경력기술서 원문)에서 LLM으로 추출한 경험 태그 캐시
    (2026-09-14 도입 — "경력기술서는 자주 안 바뀌는데 돌릴 때마다 매번 다시
    추출하는 것 아니냐"는 지적 확인 결과: ai/assignee_mapping/agent.py에
    프로세스 메모리 캐시(_experience_tags_cache)와 "호출부가 이전 실행에서
    영속시켜 둔 태그를 known_experience_tags로 넘기면 시드한다"는 훅까지
    이미 있었지만, 정작 백엔드(tasks/services.py)가 그 값을 채워 넘긴 적이
    없어 사실상 서버 재시작마다(그리고 gunicorn 워커가 여러 개면 워커마다)
    매번 새로 LLM을 호출하고 있었다. 이 테이블이 그 "영속" 역할을 한다.

    text_hash를 원문(career_history_text)의 SHA-256으로 잡아서, 원문이 한
    글자라도 바뀌면 해시가 달라져 자동으로 새 캐시로 취급된다 — 별도 무효화
    로직이 필요 없다.
    """
    text_hash = models.CharField(max_length=64, primary_key=True, verbose_name="경력기술서 원문 SHA-256")
    tags = models.JSONField(default=list, verbose_name="추출된 경험 태그")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "employee_experience_tag_cache"
        verbose_name = "경력기술서 태그 캐시"
        verbose_name_plural = "경력기술서 태그 캐시 목록"

    def __str__(self):
        return f"{self.text_hash[:12]}… ({len(self.tags)}개 태그)"

    def __str__(self):
        return f"[{self.status}] spec={self.spec_id} ({self.stage})"

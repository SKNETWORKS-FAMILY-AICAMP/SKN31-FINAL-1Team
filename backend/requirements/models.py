import uuid
from django.db import models
from django.conf import settings
from common.models import CommonCode


class RequirementDefinition(models.Model):
    """
    3단계 - 요구사항 정의서 헤더 (requirement_definition)
    """
    spec = models.ForeignKey(
        'meetings.SpecDocument',
        on_delete=models.CASCADE,
        related_name="requirement_definitions",
        verbose_name="관련 기획서"
    )
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requirement_definitions",
        verbose_name="소속 프로젝트"
    )
    title = models.CharField(max_length=200, verbose_name="요구사항 정의서 제목")
    version = models.CharField(max_length=20, default="v1.0", verbose_name="버전")
    parent_definition = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='revisions', verbose_name="이전 요구사항정의서 버전",
    )
    description = models.TextField(null=True, blank=True, verbose_name="설명")
    
    # [추가] 승인/반려 상태 필드 (common_code의 REQSPEC_STATUS 그룹 연동)
    status_code = models.ForeignKey(
        CommonCode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="req_definition_status",
        limit_choices_to={'group_id': 'REQSPEC_STATUS'},
        verbose_name="승인 상태"
    )

    # 기획서(SpecDocument.review_comment)에는 있는데 요구사항정의서엔 없어서, PM이
    # 반려해도 사유 없이 상태만 바뀌던 문제를 고친다(팀 전달 목록에 있던 항목).
    reject_reason = models.TextField(null=True, blank=True, verbose_name="반려 사유")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_requirements",
        verbose_name="작성자"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성 일시")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정 일시")

    class Meta:
        db_table = "requirement_definition"
        verbose_name = "요구사항 정의서"
        verbose_name_plural = "요구사항 정의서 목록"

    def __str__(self):
        status_str = self.status_code.code_name if self.status_code else "미지정"
        return f"[{self.id}] {self.title} ({self.version}) - {status_str}"


class RequirementItem(models.Model):
    """
    3단계 - 요구사항 상세 항목 (requirement_item)
    예: REQ-01 로그인 기능, REQ-02 결제 연동 등
    """
    req_def = models.ForeignKey(
        RequirementDefinition,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="요구사항 정의서"
    )
    req_code = models.CharField(max_length=50, verbose_name="요구사항 코드 (예: REQ-01)")
    req_name = models.CharField(max_length=200, verbose_name="요구사항명")
    description = models.TextField(verbose_name="요구사항 상세 내용")
    related_feature = models.TextField(blank=True, default="")
    input_output = models.TextField(blank=True, default="")
    acceptance_criteria = models.TextField(blank=True, default="")
    note = models.TextField(blank=True, default="")
    source = models.TextField(blank=True, default="")
    review_status = models.TextField(blank=True, default="")

    
    # 우선순위 (common 앱의 CommonCode 연동 - 예: HIGH, MEDIUM, LOW)
    priority_code = models.ForeignKey(
        CommonCode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="req_priority",
        verbose_name="우선순위"
    )
    
    difficulty = models.CharField(max_length=20, null=True, blank=True, verbose_name="난이도 (상/중/하)")
    category = models.CharField(max_length=50, null=True, blank=True, verbose_name="기능 카테고리")
    category_2 = models.CharField(max_length=50, null=True, blank=True, verbose_name="기능 카테고리 2")

    # 화면의 "순번" 표시 순서 — 프론트에서 특정 행 사이에 항목을 끼워 넣을 수 있도록
    # 정수가 아닌 실수로 둔다(두 항목 사이 값 = 중간값을 매기면 다른 행의 순서를 안
    # 건드리고 끼워넣을 수 있다). 기본값 0은 그냥 자리표시자 — 실제 값은 생성 시점에
    # (AI 추출은 인덱스 순서대로, 수동 추가는 프론트가 넘긴 위치 기준으로) 채워진다.
    order = models.FloatField(default=0, verbose_name="표시 순서")

    class Meta:
        db_table = "requirement_item"
        verbose_name = "요구사항 상세 항목"
        verbose_name_plural = "요구사항 상세 항목 목록"
        ordering = ["order", "id"]

    def __str__(self):
        return f"[{self.req_code}] {self.req_name}"


class RequirementExtractionJob(models.Model):
    """
    "요구사항정의서 생성"/"재생성"(AI가 기획서에서 세부 항목을 뽑아내는 작업)이
    순차 LLM 호출(1회 + baseline 카테고리 누락 시 최대 MAX_RETRIES회 추가)이라
    동기 요청으로 두면 사용자가 화면을 붙잡고 기다려야 한다 — tasks.TaskGenerationJob /
    meetings.MeetingAnalysisJob과 동일한 패턴(백그라운드 스레드 + 진행 단계 폴링)을
    그대로 따른다(2026-09-15). Celery/Redis 워커 인프라가 아직 없어(다른 Job
    모델들과 동일한 사유) threading.Thread로 가볍게 구현했다.
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
        related_name='requirement_extraction_jobs', verbose_name="대상 기획서",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='requirement_extraction_jobs', verbose_name="실행자",
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING, verbose_name="상태")
    stage = models.CharField(max_length=100, default="", blank=True, verbose_name="현재 진행 단계(사람이 읽는 라벨)")
    result = models.JSONField(null=True, blank=True, verbose_name="성공 시 결과(RequirementDefinitionSerializer 데이터)")
    error_message = models.TextField(null=True, blank=True, verbose_name="실패 시 오류 메시지")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "requirement_extraction_job"
        verbose_name = "요구사항정의서 생성 실행 작업"
        verbose_name_plural = "요구사항정의서 생성 실행 작업 목록"
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.status}] spec={self.spec_id} ({self.stage})"

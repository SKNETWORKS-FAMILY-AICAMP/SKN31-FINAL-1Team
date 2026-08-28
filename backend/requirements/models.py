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
    title = models.CharField(max_length=200, verbose_name="요구사항 정의서 제목")
    version = models.CharField(max_length=20, default="v1.0", verbose_name="버전")
    description = models.TextField(null=True, blank=True, verbose_name="설명")
    
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
        return f"[{self.id}] {self.title} ({self.version})"


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

    class Meta:
        db_table = "requirement_item"
        verbose_name = "요구사항 상세 항목"
        verbose_name_plural = "요구사항 상세 항목 목록"

    def __str__(self):
        return f"[{self.req_code}] {self.req_name}"
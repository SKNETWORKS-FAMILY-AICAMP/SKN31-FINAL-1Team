# common/models.py

from django.db import models

class CommonCodeGroup(models.Model):
    """
    공통 코드 그룹 (대분류)
    예: USER_ROLE(권한), REQ_PRIORITY(우선순위), TASK_STATUS(진행상태) 등
    """
    group_code = models.CharField(
        max_length=50, 
        primary_key=True, 
        verbose_name="코드 그룹 ID"
    )
    group_name = models.CharField(
        max_length=100, 
        verbose_name="코드 그룹명"
    )
    description = models.TextField(
        null=True, 
        blank=True, 
        verbose_name="설명"
    )
    is_active = models.BooleanField(
        default=True, 
        verbose_name="사용 여부"
    )
    created_at = models.DateTimeField(
        auto_now_add=True, 
        verbose_name="생성 일시"
    )

    class Meta:
        db_table = "common_code_group"
        verbose_name = "공통 코드 그룹"
        verbose_name_plural = "공통 코드 그룹 목록"

    def __str__(self):
        return f"[{self.group_code}] {self.group_name}"


class CommonCode(models.Model):
    """
    공통 코드 상세 (중/소분류)
    예: REQ_PRIORITY 하위 -> HIGH(상), MEDIUM(중), LOW(하)
    """
    code_id = models.CharField(
        max_length=50, 
        primary_key=True, 
        verbose_name="코드 ID"
    )
    group = models.ForeignKey(
        CommonCodeGroup, 
        on_delete=models.CASCADE, 
        related_name="codes", 
        db_column="group_code", 
        verbose_name="코드 그룹"
    )
    code_name = models.CharField(
        max_length=100, 
        verbose_name="코드명"
    )
    sort_order = models.IntegerField(
        default=0, 
        verbose_name="정렬 순서"
    )
    is_active = models.BooleanField(
        default=True, 
        verbose_name="사용 여부"
    )
    description = models.TextField(
        null=True, 
        blank=True, 
        verbose_name="설명"
    )
    created_at = models.DateTimeField(
        auto_now_add=True, 
        verbose_name="생성 일시"
    )

    class Meta:
        db_table = "common_code"
        ordering = ["group", "sort_order"]
        verbose_name = "공통 코드"
        verbose_name_plural = "공통 코드 목록"

    def __str__(self):
        return f"[{self.group_id}] {self.code_id} - {self.code_name}"
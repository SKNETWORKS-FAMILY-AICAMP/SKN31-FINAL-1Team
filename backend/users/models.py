from django.db import models
from django.contrib.auth.models import AbstractUser
from common.models import CommonCode


class User(AbstractUser):
    """
    커스텀 사용자 모델 (user)
    Django의 AbstractUser를 확장하여 기본 인증 기능(아이디, 패스워드 등)을 유지합니다.
    """
    emp_no = models.CharField(
        max_length=20, 
        unique=True, 
        null=True, 
        blank=True, 
        verbose_name="사원번호"
    )
    phone = models.CharField(
        max_length=20, 
        null=True, 
        blank=True, 
        verbose_name="전화번호"
    )
    
    # common 앱의 CommonCode 참조
    dept_code = models.ForeignKey(
        CommonCode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_dept",
        db_column="dept_code",
        verbose_name="부서 코드"
    )
    job_role_code = models.ForeignKey(
        CommonCode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_job_role",
        db_column="job_role_code",
        verbose_name="직무 코드"
    )
    position_code = models.ForeignKey(
        CommonCode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_position",
        db_column="position_code",
        verbose_name="직급 코드"
    )
    role_code = models.ForeignKey(
        CommonCode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_role",
        db_column="role_code",
        verbose_name="권한 코드"
    )
    status_code = models.ForeignKey(
        CommonCode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_status",
        db_column="status_code",
        verbose_name="상태 코드"
    )

    is_busy = models.BooleanField(
        default=False, 
        verbose_name="현재 작업 중 여부", 
        help_text="현재 업무가 진행 중인지 여부"
    )

    class Meta:
        db_table = "user"
        verbose_name = "사용자"
        verbose_name_plural = "사용자 목록"

    def __str__(self):
        # 성+이름 조합 (성/이름이 비어있을 경우 username 출력)
        full_name = f"{self.last_name}{self.first_name}".strip()
        return f"[{self.username}] {full_name}" if full_name else self.username


class UserSkill(models.Model):
    """
    사용자 보유 기술 스택 (user_skill)
    """
    skill_id = models.AutoField(primary_key=True, verbose_name="기술 ID")
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name="skills", 
        db_column="user_id", 
        verbose_name="사용자"
    )
    skill_code = models.ForeignKey(
        CommonCode, 
        on_delete=models.CASCADE, 
        db_column="skill_code", 
        verbose_name="기술 코드"
    )
    proficiency_level = models.IntegerField(
        default=1, 
        verbose_name="숙련도 (1~5)"
    )

    class Meta:
        db_table = "user_skill"
        verbose_name = "사용자 기술"
        verbose_name_plural = "사용자 기술 목록"

    def __str__(self):
        code_name = self.skill_code.code_name if self.skill_code else "미지정"
        return f"{self.user.username} - {code_name}"


class UserCertification(models.Model):
    """
    사용자 보유 자격증 (user_certification)
    """
    cert_id = models.AutoField(primary_key=True, verbose_name="자격증 ID")
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name="certifications", 
        db_column="user_id", 
        verbose_name="사용자"
    )
    cert_code = models.ForeignKey(
        CommonCode, 
        on_delete=models.CASCADE, 
        db_column="cert_code", 
        verbose_name="자격증 코드"
    )
    acquired_date = models.DateField(
        null=True, 
        blank=True, 
        verbose_name="취득일"
    )

    class Meta:
        db_table = "user_certification"
        verbose_name = "사용자 자격증"
        verbose_name_plural = "사용자 자격증 목록"

    def __str__(self):
        code_name = self.cert_code.code_name if self.cert_code else "미지정"
        return f"{self.user.username} - {code_name}"
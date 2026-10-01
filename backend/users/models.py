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

    # 2026-09-08: 프론트엔드 온보딩/최초 로그인 유저 판별을 위해 추가
    # False: 온보딩 미완료(신규 유저 -> 온보딩 페이지로 이동)
    # True: 온보딩 완료(기존 유저 -> 메인 페이지로 이동)
    is_onboarded = models.BooleanField(
        default=False,
        verbose_name="온보딩 완료 여부",
        help_text="최초 프로필 설정/온보딩 완료 여부"
    )

    # 2026-09-07: 한 계정당 동시 로그인 1개만 허용하기 위한 "현재 활성 세션" 표식.
    # 로그인할 때마다 새 값으로 갱신되고, 발급되는 JWT에 sid 클레임으로 심긴다.
    # 인증 시 토큰의 sid != 이 값이면(= 다른 기기에서 새로 로그인함) 그 세션을 거부한다.
    # null이면(재배포 직후 기존 세션) 아직 이 방식에 편입되지 않은 것으로 보고 허용 —
    # 다음 로그인부터 강제된다.
    session_key = models.CharField(
        max_length=32, null=True, blank=True, editable=False,
        verbose_name="현재 활성 세션 키",
    )
    # 그 세션이 마지막으로 요청을 보낸 시각. 로그인 차단 방식에서 "유휴 세션 자동 해제"에 쓴다 —
    # 이 값이 일정 시간(SESSION_IDLE_LIMIT) 넘게 갱신 안 됐으면 자리를 비운 것으로 보고
    # 다른 기기의 로그인을 허용한다(로그아웃 없이 브라우저만 닫아 계정이 영구 잠기는 것 방지).
    session_last_seen = models.DateTimeField(
        null=True, blank=True, editable=False,
        verbose_name="활성 세션 마지막 활동 시각",
    )

    # 2026-08-31: 직원관리 화면(프론트 members/page.tsx) 재설계에 필요해서 추가 — 기존 모델엔
    # 입사/퇴사일과 참여 프로젝트 이력을 담을 필드가 없었다. "참여 프로젝트"는 별도 공통코드
    # 그룹이 아직 없어(기술/자격증처럼 코드 테이블화하지 않음) 다른 필드(phone 등)와 같은 방식으로
    # 자유 텍스트(콤마 구분)로 둔다 — 나중에 프로젝트 마스터 데이터가 생기면 그때 정규화한다.
    hire_date = models.DateField(null=True, blank=True, verbose_name="입사일")
    resign_date = models.DateField(null=True, blank=True, verbose_name="퇴사일")
    past_projects = models.TextField(null=True, blank=True, verbose_name="참여 프로젝트 이력(콤마 구분)")

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
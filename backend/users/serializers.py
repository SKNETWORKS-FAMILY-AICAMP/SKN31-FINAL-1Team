# users/serializers.py

###############################################################
# 사용자 프로필 조회 및 기술 스택(UserSkill), 자격증(UserCertification), 공통 코드 정보(CommonCode)를 깔끔하게 조합
###############################################################

from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate
from django.utils import timezone
from users.models import UserSkill, UserCertification
from common.models import CommonCode
from drf_spectacular.utils import extend_schema_field

User = get_user_model()


class CommonCodeSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommonCode
        fields = ['code_id', 'code_name']


class UserSkillSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(source='skill_code.code_name', read_only=True)

    class Meta:
        model = UserSkill
        fields = ['skill_id', 'skill_code', 'skill_name', 'proficiency_level']


class UserCertificationSerializer(serializers.ModelSerializer):
    cert_name = serializers.CharField(source='cert_code.code_name', read_only=True)

    class Meta:
        model = UserCertification
        fields = ['cert_id', 'cert_code', 'cert_name', 'acquired_date']


class UserSimpleSerializer(serializers.ModelSerializer):
    """
    타 앱(tasks, meetings 등) 및 로그인 성공 응답에서 담당자/작성자/사용자 참조용 간단 Serializer
    """
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'full_name', 'emp_no', 'is_onboarded']

    @extend_schema_field(serializers.CharField())
    def get_full_name(self, obj):
        name = f"{obj.last_name}{obj.first_name}".strip()
        return name if name else obj.username


class UserDetailSerializer(serializers.ModelSerializer):
    """
    사용자 상세 프로필 및 보유 스택/자격증 포함 Serializer
    """
    dept_info = CommonCodeSimpleSerializer(source='dept_code', read_only=True)
    job_role_info = CommonCodeSimpleSerializer(source='job_role_code', read_only=True)
    position_info = CommonCodeSimpleSerializer(source='position_code', read_only=True)
    role_info = CommonCodeSimpleSerializer(source='role_code', read_only=True)
    status_info = CommonCodeSimpleSerializer(source='status_code', read_only=True)
    
    skills = UserSkillSerializer(many=True, read_only=True)
    certifications = UserCertificationSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'emp_no',
            'phone',
            'first_name',
            'last_name',
            'dept_code',
            'dept_info',
            'job_role_code',
            'job_role_info',
            'position_code',
            'position_info',
            'role_code',
            'role_info',
            'status_code',
            'status_info',
            'is_staff',
            'is_busy',
            'is_onboarded',
            'hire_date',
            'resign_date',
            'past_projects',
            'skills',
            'certifications',
        ]
        # is_staff는 화면의 "권한(role_code)" 선택과 별개로 Django 관리자 사이트 접근권한을
        # 뜻하는 내장 플래그라 이 API로 바꾸게 하면 안 된다 — role_code가 아직 기존 계정들에
        # 채워지지 않아서(시드 데이터 role_code=None) 프론트의 PM 판정 폴백으로만 읽기 전용 노출.
        read_only_fields = ['id', 'is_staff']

    def update(self, instance, validated_data):
        # 2026-09-16 (사용자 지적): 직원관리 목록의 빠른 상태 변경 드롭다운(members/page.tsx
        # handleStatusChange)은 status_code만 보내고 resign_date는 안 건드린다 — "퇴사"
        # 상태인데 퇴사일이 계속 비어있는 문제가 실제로 있었다(고시우 사례로 실측 확인).
        # 어느 경로로 오든 항상 일관되게 맞도록, status_code가 RESIGNED로 "새로" 바뀌는데
        # resign_date를 이 요청에서 명시적으로 같이 안 보냈으면 오늘 날짜로 자동 채운다
        # (이미 명시적으로 보낸 값은 그대로 존중). 반대로 RESIGNED에서 다른 상태로
        # 되돌아가면(복직 등) 남아있던 옛 퇴사일도 같이 지운다.
        if 'status_code' in validated_data and 'resign_date' not in validated_data:
            new_status = validated_data['status_code']
            new_status_id = new_status.code_id if new_status else None
            was_resigned = instance.status_code_id == 'RESIGNED'
            if new_status_id == 'RESIGNED' and not was_resigned:
                validated_data['resign_date'] = timezone.localdate()
            elif new_status_id != 'RESIGNED' and was_resigned:
                validated_data['resign_date'] = None
        return super().update(instance, validated_data)


# ===============================================================
# 직원관리(members 화면) 재설계용 Serializer — 2026-08-31 추가
# ===============================================================

class UserCreateSerializer(serializers.ModelSerializer):
    """
    신규 직원 계정 생성 전용 Serializer.
    비밀번호를 안 보내면 화면 안내 문구("초기 비밀번호: 1111")와 맞춰 기본값 1111을 쓴다 —
    반드시 온보딩/최초 로그인 시 변경하도록 운영 절차로 강제해야 한다(이 API 자체는 강제 안 함).
    """
    password = serializers.CharField(required=False, write_only=True, allow_blank=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'password', 'first_name', 'last_name', 'emp_no', 'phone',
            'dept_code', 'position_code', 'job_role_code', 'hire_date',
        ]
        read_only_fields = ['id']

    def create(self, validated_data):
        password = validated_data.pop('password', None) or '1111'
        # create_user가 비밀번호를 해싱해서 저장한다 — 절대 set_password 없이 raw로 넣지 않는다.
        user = User.objects.create_user(password=password, **validated_data)
        return user


class UserPasswordResetResponseSerializer(serializers.Serializer):
    message = serializers.CharField(default="비밀번호가 초기화되었습니다.")


# ===============================================================
# 로그인 관련 Serializers (추가)
# ===============================================================

class LoginRequestSerializer(serializers.Serializer):
    """
    로그인 요청 시 아이디/비밀번호 검증
    """
    username = serializers.CharField(required=True, help_text="사용자 아이디")
    password = serializers.CharField(required=True, write_only=True, help_text="비밀번호")

    def validate(self, attrs):
        username = attrs.get('username')
        password = attrs.get('password')

        user = authenticate(username=username, password=password)

        if not user:
            raise serializers.ValidationError("아이디 또는 비밀번호가 올바르지 않습니다.")
        if not user.is_active:
            raise serializers.ValidationError("비활성화된 계정입니다.")

        attrs['user'] = user
        return attrs


class LoginResponseSerializer(serializers.Serializer):
    """
    Swagger(drf-spectacular) 문서화를 위한 로그인 성공 응답 구조
    """
    message = serializers.CharField(default="로그인 성공")
    user = UserSimpleSerializer()
    access = serializers.CharField(help_text="JWT Access Token — 이후 요청의 Authorization: Bearer 헤더에 사용")
    refresh = serializers.CharField(help_text="JWT Refresh Token — access 토큰 재발급 및 로그아웃 시 블랙리스트 처리에 사용")
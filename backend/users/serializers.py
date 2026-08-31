# users/serializers.py

###############################################################
# 사용자 프로필 조회 및 기술 스택(UserSkill), 자격증(UserCertification), 공통 코드 정보(CommonCode)를 깔끔하게 조합
###############################################################

from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate
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
    타 앱(tasks, meetings 등)에서 담당자/작성자 참조용 간단 Serializer
    """
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'full_name', 'emp_no']

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
            'is_busy',
            'skills',
            'certifications',
        ]
        read_only_fields = ['id']

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
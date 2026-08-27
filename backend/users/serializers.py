###############################################################
# 사용자 프로필 조회 및 기술 스택(UserSkill), 자격증(UserCertification), 공통 코드 정보(CommonCode)를 깔끔하게 조합
###############################################################

from rest_framework import serializers
from django.contrib.auth import get_user_model
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
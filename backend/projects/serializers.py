###############################################################
# 프로젝트 기본 정보(Project) 및 프론트엔드 /history 타임라인 페이지와 연동되는 통합 이력 로그(PipelineHistory) 전용 Serializer
###############################################################

from rest_framework import serializers
from projects.models import Project, PipelineHistory
from users.serializers import UserSimpleSerializer


class ProjectSerializer(serializers.ModelSerializer):
    """
    프로젝트 목록 및 상세 조회용 Serializer
    """
    owner_name = serializers.CharField(source='owner.username', read_only=True)

    class Meta:
        model = Project
        fields = [
            'id',
            'name',
            'description',
            'owner',
            'owner_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class PipelineHistorySerializer(serializers.ModelSerializer):
    """
    /history 페이지 타임라인 및 로그 조회용 Serializer
    """
    step_type_display = serializers.CharField(source='get_step_type_display', read_only=True)
    actor_info = UserSimpleSerializer(source='actor', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)

    class Meta:
        model = PipelineHistory
        fields = [
            'id',
            'project',
            'project_name',
            'meeting',
            'spec',
            'requirement',
            'task',
            'step_type',
            'step_type_display',
            'title',
            'description',
            'actor',
            'actor_info',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class PipelineHistoryCreateSerializer(serializers.ModelSerializer):
    """
    파이프라인 진행 상태 변경 시 이력 로그 기록 전용 Serializer
    """
    class Meta:
        model = PipelineHistory
        fields = [
            'project',
            'meeting',
            'spec',
            'requirement',
            'task',
            'step_type',
            'title',
            'description',
            'actor',
        ]
from rest_framework import serializers
from requirements.models import RequirementDefinition, RequirementItem
from common.models import CommonCode


class CommonCodeSimpleSerializer(serializers.ModelSerializer):
    """
    우선순위 및 상태 등 공통코드 조회용 단순 Serializer
    """
    class Meta:
        model = CommonCode
        fields = ['code_id', 'code_name']


class RequirementItemSerializer(serializers.ModelSerializer):
    """
    요구사항 상세 항목(RequirementItem) 조회 및 생성/수정용 Serializer
    """
    priority_info = CommonCodeSimpleSerializer(source='priority_code', read_only=True)

    class Meta:
        model = RequirementItem
        fields = [
            'id',
            'req_def',
            'req_code',
            'req_name',
            'description',
            'priority_code',
            'priority_info',
            'difficulty',
            'category',
            'category_2',
        ]
        read_only_fields = ['id']


class RequirementDefinitionSerializer(serializers.ModelSerializer):
    """
    요구사항 정의서(RequirementDefinition) 상세 조회 및 수정용 Serializer
    하위에 속한 모든 요구사항 상세 항목(items), spec_id, 승인/반려 상태(status) 포함.
    """
    spec_id = serializers.IntegerField(source='spec.spec_id', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    spec_title = serializers.CharField(source='spec.title', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    
    # 승인/반려 상태 조회용 표현 (읽기 전용)
    status_info = CommonCodeSimpleSerializer(source='status_code', read_only=True)
    
    items = RequirementItemSerializer(many=True, read_only=True)

    class Meta:
        model = RequirementDefinition
        fields = [
            'id',
            'spec',
            'spec_id',
            'spec_title',
            'project',
            'project_name',
            'title',
            'version',
            'description',
            'status_code',    # 상태 변경(승인/반려) 수정을 위한 FK 필드
            'status_info',    # 상태 코드/명칭 조회를 위한 객체 필드
            'created_by',
            'created_by_name',
            'items',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class RequirementDefinitionCreateSerializer(serializers.ModelSerializer):
    """
    요구사항 정의서 신규 생성용 Serializer (spec_id를 통한 FK 매핑 보장)
    """
    spec_id = serializers.PrimaryKeyRelatedField(
        source='spec',
        queryset=RequirementDefinition._meta.get_field('spec').remote_field.model.objects.all(),
        required=False,
        write_only=True
    )

    class Meta:
        model = RequirementDefinition
        fields = ['spec', 'spec_id', 'project', 'title', 'version', 'description', 'status_code']

    def validate(self, attrs):
        if 'spec' not in attrs:
            raise serializers.ValidationError({"spec_id": "요구사항 정의서 생성 시 spec_id(기획서 ID)는 필수입니다."})
        return attrs
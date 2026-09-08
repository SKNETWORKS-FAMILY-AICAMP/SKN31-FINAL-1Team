from rest_framework import serializers
from requirements.models import RequirementDefinition, RequirementItem
from common.models import CommonCode


class CommonCodeSimpleSerializer(serializers.ModelSerializer):
    """
    우선순위 등 공통코드 조회용 단순 Serializer
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
    요구사항 정의서(RequirementDefinition) 상세 조회용 Serializer
    하위에 속한 모든 요구사항 상세 항목(items) 및 spec_id 포함.
    """
    spec_id = serializers.IntegerField(source='spec.spec_id', read_only=True)  # spec.spec_id 참조로 변경
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    spec_title = serializers.CharField(source='spec.title', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    items = RequirementItemSerializer(many=True, read_only=True)

    class Meta:
        model = RequirementDefinition
        fields = [
            'id',
            'spec',
            'spec_id',         # 추가된 필드
            'spec_title',
            'project',
            'project_name',
            'title',
            'version',
            'description',
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
    # 프론트엔드에서 'spec' 대신 'spec_id' 키로 넘어올 경우를 위해 PrimaryKeyRelatedField 설정
    spec_id = serializers.PrimaryKeyRelatedField(
        source='spec',
        queryset=RequirementDefinition._meta.get_field('spec').remote_field.model.objects.all(),
        required=False,
        write_only=True
    )

    class Meta:
        model = RequirementDefinition
        fields = ['spec', 'spec_id', 'project', 'title', 'version', 'description']

    def validate(self, attrs):
        # 'spec' 또는 'spec_id' 중 하나라도 입력되지 않았을 경우 예외 처리
        if 'spec' not in attrs:
            raise serializers.ValidationError({"spec_id": "요구사항 정의서 생성 시 spec_id(기획서 ID)는 필수입니다."})
        return attrs
###############################################################
# requirements 앱은 요구사항 정의서 헤더(RequirementDefinition)와 상세 요구사항 항목(RequirementItem)을 다룸.
# 상세 항목들을 한눈에 조회할 수 있도록 중첩(Nested) 구조를 포함하여 작성.
#
# RequirementItemSerializer: 
## REQ-01, REQ-02 등 개별 요구사항 항목의 우선순위 코드명(priority_info)을 포함하여 프론트엔드에서 직관적으로 표시
# RequirementDefinitionSerializer: 
## 요구사항 정의서 1건을 조회할 때 연관된 기획서 제목(spec_title)과 속한 요구사항 상세 목록(items)을 한 번에 내려주도록 처리
###############################################################

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
        ]
        read_only_fields = ['id']


class RequirementDefinitionSerializer(serializers.ModelSerializer):
    """
    요구사항 정의서(RequirementDefinition) 상세 조회용 Serializer
    하위에 속한 모든 요구사항 상세 항목(items)을 포함합니다.
    """
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    spec_title = serializers.CharField(source='spec.title', read_only=True)
    items = RequirementItemSerializer(many=True, read_only=True)

    class Meta:
        model = RequirementDefinition
        fields = [
            'id',
            'spec',
            'spec_title',
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
    요구사항 정의서 신규 생성용 Serializer
    """
    class Meta:
        model = RequirementDefinition
        fields = ['spec', 'title', 'version', 'description']
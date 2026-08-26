#common/serializers.py

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from common.models import CommonCode


class CommonCodeSerializer(serializers.ModelSerializer):
    """
    공통 코드 전체 필드 조회용 Serializer
    """
    # FK 관계인 group의 group_code 문자열을 읽어옴
    group_code = serializers.ReadOnlyField(source='group.group_code')

    class Meta:
        model = CommonCode
        fields = [
            'code_id',
            'group_code',
            'code_name',
            'sort_order',
            'is_active',   # is_use -> is_active로 수정
            'description', # 모델에 정의된 설명 필드 추가
            'created_at',
        ]
        read_only_fields = ['created_at']


class CommonCodeSimpleSerializer(serializers.ModelSerializer):
    """
    다른 앱(users, meetings, requirements 등)에서 
    드롭다운이나 상태 표시용으로 참조하는 가벼운 Serializer
    """
    class Meta:
        model = CommonCode
        fields = ['code_id', 'code_name']
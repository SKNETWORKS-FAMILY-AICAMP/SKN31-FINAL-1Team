###############################################################
# tasks 앱은 요구사항 항목(RequirementItem)을 기반으로 자동/수동 배정된 업무(TaskAssignment)를 관리
# 담당자(assigned_user) 정보와 연관된 요구사항 코드/이름을 쉽게 확인할 수 있도록 작성
#
# 연관 데이터 직관성: req_code, req_name, assigned_user_name을 읽기 전용 필드로 추가하여, 
## 프론트엔드에서 번거로운 추가 API 호출 없이 요구사항 번호와 담당자 이름을 즉시 렌더링
# TaskStatusUpdateSerializer: 
## 팀장 승인(APPROVED)이나 개발자의 진행 상태 변경 시 필요한 필드만 최소한으로 넘겨 검증 및 업데이트하도록 분리
###############################################################

from rest_framework import serializers
from tasks.models import TaskAssignment
from users.serializers import UserSimpleSerializer  # users 앱에서 정의할 간단 유저 Serializer 참조 가능


class TaskAssignmentSerializer(serializers.ModelSerializer):
    """
    배정된 업무(TaskAssignment) 목록 및 상세 조회용 Serializer
    """
    assigned_user_name = serializers.CharField(source='assigned_user.username', read_only=True)
    req_code = serializers.CharField(source='req_item.req_code', read_only=True)
    req_name = serializers.CharField(source='req_item.req_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = TaskAssignment
        fields = [
            'id',
            'req_item',
            'req_code',
            'req_name',
            'assigned_user',
            'assigned_user_name',
            'task_title',
            'task_description',
            'status',
            'status_display',
            'start_date',
            'due_date',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class TaskAssignmentCreateSerializer(serializers.ModelSerializer):
    """
    업무 배정 신규 등록/생성용 Serializer
    """
    class Meta:
        model = TaskAssignment
        fields = [
            'req_item',
            'assigned_user',
            'task_title',
            'task_description',
            'start_date',
            'due_date',
        ]


class TaskStatusUpdateSerializer(serializers.ModelSerializer):
    """
    업무 상태 변경 전용 Serializer (예: 승인 완료, 진행 중, 완료 처리)
    """
    class Meta:
        model = TaskAssignment
        fields = ['status']
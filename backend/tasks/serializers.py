###############################################################
# tasks 앱은 요구사항 항목(RequirementItem)을 기반으로 자동/수동 배정된 업무(TaskAssignment)를 관리
# 담당자(assigned_user) 정보와 연관된 요구사항 코드/이름을 쉽게 확인할 수 있도록 작성
#
# 2026-09-07: task_assignment 컬럼 재설계에 맞춰 전면 수정.
#   task_title/task_description/status → title/description/status_code(CommonCode FK)
#   due_date → end_date, Git 연동·에픽·배정근거 필드 추가.
###############################################################

from rest_framework import serializers
from tasks.models import TaskAssignment, TaskStatusCode


class _CodeSimpleSerializer(serializers.Serializer):
    """CommonCode 표시용(코드ID + 코드명)."""
    code_id = serializers.CharField(read_only=True)
    code_name = serializers.CharField(read_only=True)


class TaskAssignmentSerializer(serializers.ModelSerializer):
    """
    배정된 업무(TaskAssignment) 목록 및 상세 조회용 Serializer
    """
    # 담당자를 아이디(demo25)가 아니라 실명으로 보여달라는 요청 — 성+이름 조합이
    # 비어있는 계정(시드 데이터 등)만 username으로 대체한다(User.__str__과 동일 규칙).
    assigned_user_name = serializers.SerializerMethodField()
    req_code = serializers.CharField(source='req_item.req_code', read_only=True)
    req_name = serializers.CharField(source='req_item.req_name', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)

    status_info = _CodeSimpleSerializer(source='status_code', read_only=True)
    difficulty_info = _CodeSimpleSerializer(source='difficulty_code', read_only=True)
    git_status_info = _CodeSimpleSerializer(source='git_status_code', read_only=True)

    def get_assigned_user_name(self, obj):
        u = obj.assigned_user
        full_name = f"{u.last_name}{u.first_name}".strip()
        return full_name or u.username

    def update(self, instance, validated_data):
        # 2026-09-16 (사용자 요청): 진행률과 상태(승인됨 ↔ 진행 중)를 양방향으로 맞춘다.
        #   - 진행률을 1% 이상으로 올리면 "승인됨" → "진행 중"으로 자동 전환 (착수 신호)
        #   - 진행률을 다시 0%로 내리면 "진행 중" → "승인됨"으로 자동 되돌림 (착수 취소 신호)
        # 이 요청(TaskDetailModal의 일반 PATCH)에서 status_code를 명시적으로 같이
        # 보낸 경우엔 그 값을 그대로 존중하고 자동 전환하지 않는다.
        new_progress = validated_data.get('progress', instance.progress)
        if 'status_code' not in validated_data and new_progress is not None:
            if instance.status_code_id == TaskStatusCode.APPROVED and new_progress >= 1:
                instance.status_code_id = TaskStatusCode.IN_PROGRESS
            elif instance.status_code_id == TaskStatusCode.IN_PROGRESS and new_progress <= 0:
                instance.status_code_id = TaskStatusCode.APPROVED
        return super().update(instance, validated_data)

    class Meta:
        model = TaskAssignment
        fields = [
            'id',
            'task_no',
            'req_item',
            'req_code',
            'req_name',
            'project',
            'project_name',
            'assigned_user',
            'assigned_user_name',
            'title',
            'description',
            'difficulty_reason',
            'estimated_hours',
            'assignment_reason',
            'assigned_workload',
            'reject_reason',
            'start_date',
            'end_date',
            'progress',
            'linked_branch',
            'linked_pr_number',
            'linked_pr_url',
            'status_code',
            'status_info',
            'difficulty_code',
            'difficulty_info',
            'git_status_code',
            'git_status_info',
            'parent_task',
            'epic_no',
            'epic_title',
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
            'task_no',
            'req_item',
            'assigned_user',
            'project',
            'title',
            'description',
            'difficulty_reason',
            'estimated_hours',
            'assignment_reason',
            'assigned_workload',
            'start_date',
            'end_date',
            'status_code',
            'difficulty_code',
            'parent_task',
            'epic_no',
            'epic_title',
        ]


class TaskStatusUpdateSerializer(serializers.ModelSerializer):
    """
    업무 상태 변경 전용 Serializer (예: 승인 완료, 진행 중, 완료 처리, 반려)
    status_code 는 common_code(group_code='TASK_STATUS')의 code_id 를 받는다.
    """
    class Meta:
        model = TaskAssignment
        fields = ['status_code', 'reject_reason']

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
    # 2026-09-16 (사용자 요청): 담당자를 재배정하면 원래 AI가 누굴 추천했었는지 화면에서
    # 알 수 없어졌다는 지적 — original_assigned_user(확정 시점에 보존해둔 값, 이후 안 바뀜)의
    # 이름을 같이 내려준다. 재배정된 적 없는 업무는 원래 담당자 = 현재 담당자와 같다.
    original_assigned_user_name = serializers.SerializerMethodField()
    req_code = serializers.CharField(source='req_item.req_code', read_only=True)
    req_name = serializers.CharField(source='req_item.req_name', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)

    status_info = _CodeSimpleSerializer(source='status_code', read_only=True)
    difficulty_info = _CodeSimpleSerializer(source='difficulty_code', read_only=True)
    git_status_info = _CodeSimpleSerializer(source='git_status_code', read_only=True)

    def _display_name(self, u):
        if u is None:
            return None
        full_name = f"{u.last_name}{u.first_name}".strip()
        return full_name or u.username

    def get_assigned_user_name(self, obj):
        return self._display_name(obj.assigned_user)

    def get_original_assigned_user_name(self, obj):
        return self._display_name(obj.original_assigned_user)

    def update(self, instance, validated_data):
        # 2026-09-16 (사용자 요청): 담당자가 배정을 승인했거나(TASK_APPROVED) 이미 착수한
        # (IN_PROGRESS) 업무는 중간에 담당자를 바꿔치기할 수 없다 — 프론트(documents/page.tsx,
        # TaskDetailModal.tsx)에서 드롭박스를 잠갔지만, API를 직접 호출해 우회하는 것도
        # 막는다.
        if 'assigned_user' in validated_data:
            new_assignee = validated_data['assigned_user']
            if (
                new_assignee is not None
                and new_assignee != instance.assigned_user
                and instance.status_code_id in (TaskStatusCode.APPROVED, TaskStatusCode.IN_PROGRESS, TaskStatusCode.COMPLETED)
            ):
                raise serializers.ValidationError(
                    {"assigned_user": "승인·진행 중이거나 완료된 업무는 담당자를 변경할 수 없습니다."}
                )
            # 2026-09-16 (사용자 지적): assignment_reason(기술적합도/업무여유도/유사경험)은
            # AI가 "원래 추천했던 담당자"를 기준으로 판단한 근거 문장이다. PM이 다른 사람으로
            # 재배정하면 그 문장은 새 담당자한테 안 맞는 말이 되는데(재계산은 안 하기로
            # 했음 — 비용·일관성 문제, 이전 대화 참고), 그렇다고 옛 근거를 그대로 두면
            # 마치 새 담당자를 놓고 판단한 것처럼 오해를 준다. 재계산 대신 "이건 AI 추천이
            # 아니라 PM이 직접 정한 배정"이라고 정직하게 표시한다.
            # 2026-09-16 (추가 지적): 다른 사람으로 바꿨다가 다시 원래(AI가 최초 추천한)
            # 담당자로 되돌리면, 지워졌던 원래 근거가 복원돼야 한다 — original_assigned_user/
            # original_assignment_reason(확정 시점에 보존해둔 값)과 비교해서 판단한다.
            if new_assignee is not None and new_assignee != instance.assigned_user:
                if (
                    instance.original_assigned_user_id is not None
                    and new_assignee.pk == instance.original_assigned_user_id
                ):
                    instance.assignment_reason = instance.original_assignment_reason
                else:
                    note = "PM이 직접 재배정한 담당자입니다 (AI 추천 근거 아님)"
                    instance.assignment_reason = f"{note} / {note} / {note}"

        # 2026-09-16 (사용자 요청): 진행률과 상태(승인됨 ↔ 진행 중 ↔ 완료)를 양방향으로 맞춘다.
        #   - 진행률을 1% 이상으로 올리면 "승인됨" → "진행 중" (착수 신호)
        #   - 진행률을 다시 0%로 내리면 "진행 중" → "승인됨" (착수 취소 신호)
        #   - 진행률이 100%가 되면 "진행 중" → "완료" (완료 신호, is_busy 해제도 같이 처리)
        #   - 완료 후 100% 밑으로 다시 내리면 "완료" → "진행 중" (재오픈, is_busy 다시 걸어줌)
        # 이 요청(TaskDetailModal의 일반 PATCH)에서 status_code를 명시적으로 같이
        # 보낸 경우엔 그 값을 그대로 존중하고 자동 전환하지 않는다.
        new_progress = validated_data.get('progress', instance.progress)
        if 'status_code' not in validated_data and new_progress is not None:
            if instance.status_code_id == TaskStatusCode.APPROVED and new_progress >= 1:
                instance.status_code_id = TaskStatusCode.IN_PROGRESS
            elif instance.status_code_id == TaskStatusCode.IN_PROGRESS and new_progress <= 0:
                instance.status_code_id = TaskStatusCode.APPROVED

            # 위에서 방금 IN_PROGRESS로 바뀐 경우(승인됨 0% -> 100%로 한 번에 올린 경우)도
            # 여기서 이어서 완료 처리되도록, elif로 안 묶고 별도 if로 다시 검사한다.
            if instance.status_code_id == TaskStatusCode.IN_PROGRESS and new_progress >= 100:
                instance.status_code_id = TaskStatusCode.COMPLETED
                assigned_dev = instance.assigned_user
                if assigned_dev:
                    # TaskStatusUpdateView.patch()의 COMPLETED 처리와 동일한 규칙 —
                    # 다른 미완료 업무가 없을 때만 담당자의 is_busy를 해제한다.
                    other_open_tasks = TaskAssignment.objects.filter(
                        assigned_user=assigned_dev
                    ).exclude(pk=instance.pk).exclude(status_code_id=TaskStatusCode.COMPLETED)
                    if not other_open_tasks.exists():
                        assigned_dev.is_busy = False
                        assigned_dev.save(update_fields=['is_busy'])
            elif instance.status_code_id == TaskStatusCode.COMPLETED and new_progress < 100:
                instance.status_code_id = TaskStatusCode.IN_PROGRESS
                assigned_dev = instance.assigned_user
                if assigned_dev and not assigned_dev.is_busy:
                    assigned_dev.is_busy = True
                    assigned_dev.save(update_fields=['is_busy'])
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
            'original_assigned_user',
            'original_assigned_user_name',
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
        # original_assigned_user는 확정 시점에 한 번만 정해지고 이후 코드(services.py
        # _persist_assignments)에서만 채운다 — API 요청으로 덮어쓸 수 있는 필드가 아니다.
        read_only_fields = ['id', 'created_at', 'updated_at', 'original_assigned_user']


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

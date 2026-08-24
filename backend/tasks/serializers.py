from rest_framework import serializers
from .models import TaskAssignment
from users.serializers import UserSerializer  # 또는 사원 간단 정보 Serializer

class TaskAssignmentSerializer(serializers.ModelSerializer):
    assigned_user_name = serializers.ReadOnlyField(source='assigned_user.username')
    assigned_user_email = serializers.ReadOnlyField(source='assigned_user.email')
    spec_title = serializers.ReadOnlyField(source='spec.title')

    class Meta:
        model = TaskAssignment
        fields = [
            'id',
            'spec',
            'spec_title',
            'assigned_user',
            'assigned_user_name',
            'assigned_user_email',
            'task_title',
            'task_description',
            'status',
            'created_at'
        ]
        read_only_fields = ['status', 'created_at']
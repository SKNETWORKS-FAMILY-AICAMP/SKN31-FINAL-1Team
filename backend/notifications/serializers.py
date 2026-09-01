#notifications/serializers.py
from rest_framework import serializers
from notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'message', 'type', 'link', 'read', 'created_at']
        read_only_fields = fields

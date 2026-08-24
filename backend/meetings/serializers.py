from rest_framework import serializers
from .models import MeetingNote

class MeetingNoteSerializer(serializers.ModelSerializer):
    created_by_name = serializers.ReadOnlyField(source='created_by.username')

    class Meta:
        model = MeetingNote
        fields = [
            'id', 
            'title', 
            'content', 
            'status', 
            'created_by', 
            'created_by_name', 
            'created_at', 
            'updated_at'
        ]
        read_only_fields = ['status', 'created_by', 'created_at', 'updated_at']
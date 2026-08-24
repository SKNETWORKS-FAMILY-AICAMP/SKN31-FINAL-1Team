from rest_framework import serializers
from .models import SpecDocument

class SpecDocumentSerializer(serializers.ModelSerializer):
    meeting_title = serializers.ReadOnlyField(source='meeting.title')

    class Meta:
        model = SpecDocument
        fields = [
            'id', 
            'meeting', 
            'meeting_title', 
            'title', 
            'summary', 
            'file', 
            'status', 
            'created_at'
        ]
        read_only_fields = ['meeting', 'status', 'created_at']
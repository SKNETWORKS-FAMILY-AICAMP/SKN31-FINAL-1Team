from django.db import models
from meetings.models import MeetingNote

class SpecDocument(models.Model):
    class Status(models.TextChoices):
        GENERATING = 'GENERATING', '생성 중'
        COMPLETED = 'COMPLETED', '생성 완료'
        REVIEWED = 'REVIEWED', '검토 완료'

    meeting = models.OneToOneField(MeetingNote, on_delete=models.CASCADE, related_name='spec')
    title = models.CharField(max_length=200)
    summary = models.TextField(blank=True)
    file = models.FileField(upload_to='specs/%Y/%m/', null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.GENERATING)
    created_at = models.DateTimeField(auto_now_add=True)

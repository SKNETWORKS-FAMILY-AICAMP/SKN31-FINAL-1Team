from django.db import models

class MeetingNote(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', '작성 중'
        REVIEWED = 'REVIEWED', '검토 완료'

    title = models.CharField(max_length=200)
    content = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey('users.User', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

from django.db import models
from specs.models import SpecDocument

class TaskAssignment(models.Model):
    class Status(models.TextChoices):
        PENDING_APPROVAL = 'PENDING_APPROVAL', '승인 대기'
        APPROVED = 'APPROVED', '승인 및 알림 완료'

    spec = models.ForeignKey(SpecDocument, on_delete=models.CASCADE, related_name='assignments')
    assigned_user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='tasks')
    task_title = models.CharField(max_length=200)
    task_description = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_APPROVAL)
    created_at = models.DateTimeField(auto_now_add=True)

from django.db import models

from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class Role(models.TextChoices):
        LEADER = 'LEADER', '팀장'
        MEMBER = 'MEMBER', '팀원'

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    is_busy = models.BooleanField(default=False, help_text="현재 작업 중 여부")

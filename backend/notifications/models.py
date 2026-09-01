#notifications/models.py
from django.db import models
from django.conf import settings


class Notification(models.Model):
    """
    사용자 인앱 알림 (notification)
    검토요청/승인/반려처럼 당사자가 화면을 직접 열어보기 전엔 알 방법이 없던 이벤트를 알린다.
    """
    class NotificationType(models.TextChoices):
        INFO = 'info', '정보'
        SUCCESS = 'success', '성공'
        WARNING = 'warning', '경고'
        ERROR = 'error', '오류'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="수신자",
    )
    message = models.CharField(max_length=300, verbose_name="알림 메시지")
    type = models.CharField(
        max_length=10,
        choices=NotificationType.choices,
        default=NotificationType.INFO,
        verbose_name="알림 종류",
    )
    # 클릭 시 이동할 프론트엔드 경로 (예: /documents?note=12) — 없으면 그냥 닫히기만 한다.
    link = models.CharField(max_length=300, null=True, blank=True, verbose_name="이동 링크")
    read = models.BooleanField(default=False, verbose_name="읽음 여부")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성 일시")

    class Meta:
        db_table = "notification"
        verbose_name = "알림"
        verbose_name_plural = "알림 목록"
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.user.username}] {self.message}"

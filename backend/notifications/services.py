#notifications/services.py
from django.contrib.auth import get_user_model
from notifications.models import Notification

User = get_user_model()


def notify_user(user, message, type=Notification.NotificationType.INFO, link=None):
    """특정 사용자 한 명에게 알림을 남긴다 (예: 배분/기획서 승인·반려 결과를 작성자에게)."""
    if not user:
        return
    Notification.objects.create(user=user, message=message, type=type, link=link)


def notify_all_pms(message, type=Notification.NotificationType.INFO, link=None):
    """PM(is_staff=True) 전원에게 알림을 남긴다 (예: 검토요청 발생)."""
    pms = User.objects.filter(is_staff=True, is_active=True)
    Notification.objects.bulk_create([
        Notification(user=pm, message=message, type=type, link=link) for pm in pms
    ])

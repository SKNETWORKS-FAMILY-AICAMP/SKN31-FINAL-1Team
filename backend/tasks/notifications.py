from django.core.mail import send_mail
from django.conf import settings

def send_task_assignment_notification(assignment):
    """
    개별 사원에게 업무 배정 알림을 전송하는 함수
    (필요에 따라 Slack Webhook, Firebase Push, WebSocket 등으로 확장 가능)
    """
    user = assignment.assigned_user
    subject = f"[업무 배정 알림] 새로운 업무가 할당되었습니다: {assignment.task_title}"
    message = (
        f"안녕하세요, {user.username}님.\n\n"
        f"팀장에 의해 다음 업무가 최종 승인되어 배정되었습니다.\n\n"
        f"- 업무명: {assignment.task_title}\n"
        f"- 상세 설명: {assignment.task_description}\n"
        f"- 관련 기획서: {assignment.spec.title}\n\n"
        f"대시보드에서 상세 내용을 확인해 주세요."
    )
    
    # 이메일 알림 전송 (예시)
    if user.email:
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else 'noreply@company.com',
                [user.email],
                fail_silently=True,
            )
        except Exception as e:
            print(f"알림 전송 실패 ({user.email}): {e}")
#notifications/views.py
from django.shortcuts import get_object_or_404
from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from notifications.models import Notification
from notifications.serializers import NotificationSerializer


class NotificationListView(generics.ListAPIView):
    """
    내 알림 목록 조회 API
    GET /api/notifications/
    (userId 쿼리 파라미터를 안 받는다 — 로그인한 본인 알림만 항상 request.user 기준으로 조회한다)
    """
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)


class NotificationMarkReadView(APIView):
    """
    알림 하나 읽음 처리
    PATCH /api/notifications/{id}/read/
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=['알림'], summary='알림 읽음 처리')
    def patch(self, request, pk):
        # 본인 알림만 처리 가능 — 다른 사람 알림 id를 넣어도 못 건드리게 request.user로 필터
        notif = get_object_or_404(Notification, pk=pk, user=request.user)
        notif.read = True
        notif.save(update_fields=['read'])
        return Response(NotificationSerializer(notif).data, status=status.HTTP_200_OK)


class NotificationMarkAllReadView(APIView):
    """
    내 알림 전체 읽음 처리
    PATCH /api/notifications/read-all/
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=['알림'], summary='알림 전체 읽음 처리')
    def patch(self, request):
        Notification.objects.filter(user=request.user, read=False).update(read=True)
        return Response({"message": "모든 알림을 읽음 처리했습니다."}, status=status.HTTP_200_OK)

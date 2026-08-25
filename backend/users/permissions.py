# users/permissions.py

from rest_framework import permissions

class IsOwnerOrAdmin(permissions.BasePermission):
    """
    - 본인 객체이거나 슈퍼유저(관리자)인 경우에만 수정/삭제 허용
    - 읽기(GET) 요청은 인증된 유저라면 누구든 허용
    """
    def has_object_permission(self, request, view, obj):
        # 1. GET, HEAD, OPTIONS 요청은 허용
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # 2. 객체의 주인이 본인이거나 관리자인 경우만 허용
        # (obj가 User 모델인 경우 obj == request.user, 다른 모델은 obj.user == request.user)
        is_owner = (obj == request.user) if hasattr(obj, 'password') else getattr(obj, 'user', None) == request.user
        return is_owner or request.user.is_staff

class IsAdminUserOnly(permissions.BasePermission):
    """
    관리자(is_staff=True)만 접근 가능
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff)
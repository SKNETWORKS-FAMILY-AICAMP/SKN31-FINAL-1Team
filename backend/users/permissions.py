#users/permissions.py

from rest_framework import permissions

class IsOwnerOrAdmin(permissions.BasePermission):
    """
    - 본인 객체이거나 슈퍼유저(관리자)인 경우에만 수정/삭제 허용
    - 읽기(GET) 요청은 인증된 유저라면 누구든 허용
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        
        is_owner = (obj == request.user) if hasattr(obj, 'password') else getattr(obj, 'user', None) == request.user
        return is_owner or request.user.is_staff

class IsAdminUserOnly(permissions.BasePermission):
    """
    관리자(is_staff=True)만 접근 가능
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


# --- 1단계 추가 권한 클래스 ---

class IsPMUser(permissions.BasePermission):
    """
    PM/관리자(is_staff=True) 권한 검증 클래스
    - 대시보드 통계, 기획서/요구사항 승인·반려, 업무 AI 추천 및 확정 등 PM 전용 엔드포인트에 적용
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class IsOwnerOrPM(permissions.BasePermission):
    """
    작성자/담당자 본인 또는 PM(is_staff=True) 권한 검증 클래스
    - 개별 객체 접근 권한(has_object_permission) 검증
    - obj.created_by, obj.assigned_user, obj.meeting.created_by, obj.user, 또는 obj 본인과 비교
    """
    def has_object_permission(self, request, view, obj):
        if not (request.user and request.user.is_authenticated):
            return False

        # PM/관리자인 경우 무조건 허용
        if request.user.is_staff or request.user.groups.filter(name='PM').exists():
            return True

        # 작성자(Owner) 또는 담당자(Assigned User) 여부 판단
        if obj == request.user:
            return True
        
        meeting = getattr(obj, 'meeting', None)
        meeting_owner = getattr(meeting, 'created_by', None) if meeting else None

        owner = (
            getattr(obj, 'created_by', None) or 
            getattr(obj, 'assigned_user', None) or  # TaskAssignment의 담당자 체크 추가
            getattr(obj, 'user', None) or 
            meeting_owner
        )
        
        return owner == request.user
from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from users.serializers import UserDetailSerializer, UserSimpleSerializer

User = get_user_model()


class CurrentUserProfileView(APIView):
    """
    현재 로그인한 사용자 프로필 조회/수정 API
    GET /api/users/me/
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['0단계 - 사용자 관리'],
        summary='현재 로그인 유저 프로필 조회',
        description='현재 요청을 보낸 인증된 사용자의 상세 프로필 정보(부서, 직급, 기술 스택, 자격증 등)를 조회합니다.',
        responses={200: UserDetailSerializer}
    )
    def get(self, request):
        serializer = UserDetailSerializer(request.user)
        return Response(serializer.data)


class UserListView(generics.ListAPIView):
    """
    사용자 및 개발자 목록 조회 API (업무 배정 및 참조용)
    GET /api/users/?is_busy=false
    """
    queryset = User.objects.filter(is_active=True)
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        # simple 파라미터가 들어오면 간략한 정보만 반환
        if self.request.query_params.get('simple', None) == 'true':
            return UserSimpleSerializer
        return UserDetailSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        is_busy = self.request.query_params.get('is_busy', None)
        
        if is_busy is not None:
            # is_busy=false 조건으로 현재 한가한 개발자 필터링 가능
            is_busy_bool = is_busy.lower() == 'true'
            queryset = queryset.filter(is_busy=is_busy_bool)
            
        return queryset

    @extend_schema(
        tags=['0단계 - 사용자 관리'],
        summary='사용자/개발자 목록 조회',
        description='시스템 내 활성화된 사용자 목록을 조회합니다. 업무 자동 배정을 위해 현재 작업 가능 상태(`is_busy=false`)인 유저를 필터링하거나 간략 정보(`simple=true`)만 조회할 수 있습니다.',
        parameters=[
            OpenApiParameter(
                name='is_busy',
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description='작업 진행 중 여부 필터 (true: 작업 중, false: 작업 가능)'
            ),
            OpenApiParameter(
                name='simple',
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description='간단 정보(ID, 이름, 사번)만 반환 여부 (true/false)'
            ),
        ],
        responses={200: UserDetailSerializer(many=True)}
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
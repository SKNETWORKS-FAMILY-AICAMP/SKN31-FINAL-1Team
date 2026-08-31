#users/views.py

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from users.serializers import (
    UserDetailSerializer, 
    UserSimpleSerializer, 
    LoginRequestSerializer, 
    LoginResponseSerializer
)

User = get_user_model()


class LoginView(APIView):
    """
    사용자 로그인 API
    POST /api/users/login/
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['0단계 - 사용자 관리'],
        summary='사용자 로그인',
        description='아이디와 비밀번호를 검증하여 세션 로그인을 처리합니다.',
        request=LoginRequestSerializer,
        responses={
            200: LoginResponseSerializer,
            400: OpenApiTypes.OBJECT
        }
    )
    def post(self, request):
        serializer = LoginRequestSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            # REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES가 JWTAuthentication만 등록돼
            # 있어서(config/settings.py), 여기서 Django 세션으로 로그인시켜도 그 세션 쿠키는
            # 이후 어떤 API 요청에서도 인증으로 인정되지 않았다(모든 후속 요청이 401) — 실제로
            # 로그인 응답은 200이 오지만 그 다음부터 전부 막히는 게 이 버그의 증상이었다.
            # 토큰을 실제로 발급해서 반환하도록 고친다.
            refresh = RefreshToken.for_user(user)

            return Response({
                "message": "로그인 성공",
                "user": UserSimpleSerializer(user).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    """
    사용자 로그아웃 API
    POST /api/users/logout/
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['0단계 - 사용자 관리'],
        summary='사용자 로그아웃',
        description='현재 로그인된 세션을 종료합니다. 요청 바디에 refresh 토큰을 함께 보내면'
                    ' 그 토큰을 블랙리스트 처리(재사용 방지)합니다 — 블랙리스트 앱이 아직'
                    ' 설치되지 않았다면 조용히 건너뜁니다(클라이언트가 토큰을 버리는 것만으로도'
                    ' 사실상 로그아웃되므로 로그아웃 자체를 막을 이유는 아님).',
        responses={200: OpenApiTypes.OBJECT}
    )
    def post(self, request):
        refresh_token = request.data.get("refresh")
        if refresh_token:
            try:
                RefreshToken(refresh_token).blacklist()
            except Exception:
                pass
        return Response({"message": "로그아웃되었습니다."}, status=status.HTTP_200_OK)


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
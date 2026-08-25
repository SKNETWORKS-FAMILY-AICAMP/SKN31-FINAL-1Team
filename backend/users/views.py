# users/views.py

from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

# 💡 커스텀 권한 클래스 import (users/permissions.py 파일 생성 필요)
from .permissions import IsOwnerOrAdmin
from .serializers import (
    RegisterSerializer,
    UserSerializer,
    UserUpdateSerializer
)

User = get_user_model()


# 1. SimpleJWT 토큰 커스텀 뷰
@extend_schema(
    tags=["유저"],
    summary="로그인 (JWT 토큰 발급)",
    description="아이디와 비밀번호를 받아 Access 및 Refresh 토큰을 발급합니다."
)
class CustomTokenObtainPairView(TokenObtainPairView):
    pass


@extend_schema(
    tags=["유저"],
    summary="JWT 토큰 재발급",
    description="Refresh 토큰을 전달받아 새로운 Access 토큰을 재발급합니다."
)
class CustomTokenRefreshView(TokenRefreshView):
    pass


# 2. 유저 관리 ViewSet
@extend_schema_view(
    tags=["유저"],
    list=extend_schema(summary="유저 목록 조회"),
    create=extend_schema(summary="회원가입"),
    retrieve=extend_schema(summary="유저 상세 조회"),
    update=extend_schema(summary="유저 정보 전체 수정"),
    partial_update=extend_schema(summary="유저 정보 부분 수정"),
    destroy=extend_schema(summary="유저 삭제"),
)
class UserViewSet(viewsets.ModelViewSet):
    """
    유저 관련 API (회원가입, 조회, 정보수정)
    """
    queryset = User.objects.all()

    def get_serializer_class(self):
        if self.action == 'create':
            return RegisterSerializer
        elif self.action in ['update', 'partial_update', 'change_password']:
            return UserUpdateSerializer
        elif self.action == 'me':
            if self.request.method in ['PATCH', 'PUT']:
                return UserUpdateSerializer
            return UserSerializer
        return UserSerializer

    # 💡 요청(Action)별 상세 인가(Permission) 설정
    def get_permissions(self):
        # 1. 회원가입(POST): 누구나 가능
        if self.action == 'create':
            return [AllowAny()]
        
        # 2. 유저 전체 목록 조회(GET) 및 삭제(DELETE): 관리자만 가능
        elif self.action in ['list', 'destroy']:
            return [IsAdminUser()]
        
        # 3. 내 정보 조회/수정(me) 또는 개별 유저 수정(update, partial_update): 본인 또는 관리자만 가능
        elif self.action in ['update', 'partial_update', 'me']:
            return [IsOwnerOrAdmin()]

        # 4. 기타 요청: 기본 로그인 필요
        return [IsAuthenticated()]

    @extend_schema(
        methods=["GET"],
        tags=["유저"],
        summary="내 정보 조회",
        description="로그인된 사용자의 본인 프로필 정보를 조회합니다.",
        responses={200: UserSerializer}
    )
    @extend_schema(
        methods=["PATCH"],
        tags=["유저"],
        summary="내 비밀번호 수정",
        description="로그인된 사용자의 비밀번호를 수정합니다.",
        request=UserUpdateSerializer,
        responses={200: OpenApiResponse(description="비밀번호 변경 완료")}
    )
    @action(detail=False, methods=['get', 'patch'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """
        GET /api/v1/users/me/   -> 본인 정보 조회
        PATCH /api/v1/users/me/ -> 본인 비밀번호 변경
        """
        user = request.user

        if request.method == 'GET':
            serializer = self.get_serializer(user)
            return Response(serializer.data, status=status.HTTP_200_OK)

        elif request.method == 'PATCH':
            serializer = self.get_serializer(user, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(
                {"message": "비밀번호가 성공적으로 변경되었습니다."},
                status=status.HTTP_200_OK
            )
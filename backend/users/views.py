#users/views.py

from django.conf import settings
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from users.serializers import (
    UserDetailSerializer,
    UserSimpleSerializer,
    UserCreateSerializer,
    UserPasswordResetResponseSerializer,
    LoginRequestSerializer,
    LoginResponseSerializer,
)
from users.permissions import IsAdminUserOnly
from users.jwt_cookies import set_auth_cookies, clear_auth_cookies, REFRESH_COOKIE, REFRESH_COOKIE_PATH
from common.models import CommonCode

User = get_user_model()


class CsrfCookieView(APIView):
    """
    CSRF 쿠키 발급용 — 로그인 화면 진입 시 프론트가 한 번 불러서 csrftoken 쿠키를 미리
    받아둔다. HttpOnly 쿠키(access/refresh)로 인증을 옮기면서 CSRF 검증이 다시 필요해졌는데,
    Django의 csrftoken 쿠키는 이렇게 명시적으로 한 번 "발급을 트리거"해야 내려온다
    (@ensure_csrf_cookie 없이는 요청이 CSRF 토큰을 안 쓰면 쿠키 자체가 안 생김).
    GET /api/users/csrf/
    """
    permission_classes = [permissions.AllowAny]

    @method_decorator(ensure_csrf_cookie)
    @extend_schema(
        tags=['0단계 - 사용자 관리'],
        summary='CSRF 쿠키 발급',
        description='csrftoken 쿠키를 발급합니다. 로그인 등 쓰기 요청 전에 먼저 호출해야 합니다.',
        responses={200: OpenApiTypes.OBJECT}
    )
    def get(self, request):
        return Response({"detail": "csrf cookie set"})


class LoginView(APIView):
    """
    사용자 로그인 API
    POST /api/users/login/
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['0단계 - 사용자 관리'],
        summary='사용자 로그인',
        description='아이디와 비밀번호를 검증하고, access/refresh JWT를 HttpOnly 쿠키로 내려줍니다.',
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
            refresh = RefreshToken.for_user(user)

            response = Response({
                "message": "로그인 성공",
                "user": UserSimpleSerializer(user).data,
            }, status=status.HTTP_200_OK)
            # 2026-08-31: localStorage 대신 HttpOnly 쿠키로 토큰을 내려준다 — localStorage는
            # XSS 한 방이면 JS가 그대로 읽어갈 수 있지만, HttpOnly 쿠키는 JS가 아예 접근할 수
            # 없다. 응답 본문에는 더 이상 access/refresh를 담지 않는다(담으면 결국 프론트가
            # 어딘가에 저장해야 하고, 그게 localStorage면 의미가 없어진다).
            set_auth_cookies(response, str(refresh.access_token), str(refresh))
            # 로그인 직후 바로 쓰기 요청(예: 다음 화면의 POST)이 CSRF 토큰을 요구하므로,
            # 이 시점에 csrftoken 쿠키도 같이 보장해준다.
            get_token(request)
            return response

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
        description='refresh 토큰 쿠키를 블랙리스트 처리하고, access/refresh 쿠키를 지웁니다.',
        responses={200: OpenApiTypes.OBJECT}
    )
    def post(self, request):
        refresh_token = request.COOKIES.get(REFRESH_COOKIE)
        if refresh_token:
            try:
                RefreshToken(refresh_token).blacklist()
            except Exception:
                pass
        response = Response({"message": "로그아웃되었습니다."}, status=status.HTTP_200_OK)
        clear_auth_cookies(response)
        # DEV 계정전환 중이었다면 그 흔적도 같이 지운다.
        response.delete_cookie('dev_original_access_token', path='/')
        response.delete_cookie('dev_original_refresh_token', path=REFRESH_COOKIE_PATH)
        return response


class CookieTokenRefreshView(APIView):
    """
    access 토큰 재발급 API — refresh 토큰을 쿠키에서 읽는다(요청 바디 불필요).
    POST /api/users/token-refresh/
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['0단계 - 사용자 관리'],
        summary='access 토큰 재발급',
        description='refresh_token 쿠키로 새 access 토큰을 발급해 쿠키로 내려줍니다.',
        responses={200: OpenApiTypes.OBJECT, 401: OpenApiTypes.OBJECT}
    )
    def post(self, request):
        refresh_token = request.COOKIES.get(REFRESH_COOKIE)
        if not refresh_token:
            return Response({"detail": "refresh 토큰이 없습니다."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            refresh = RefreshToken(refresh_token)
        except TokenError as e:
            return Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)

        response = Response({"detail": "재발급 완료"}, status=status.HTTP_200_OK)
        set_auth_cookies(response, str(refresh.access_token))
        return response


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


class UserListView(generics.ListCreateAPIView):
    """
    사용자 및 개발자 목록 조회 API (업무 배정 및 참조용)
    GET /api/users/?is_busy=false
    POST /api/users/ — 직원관리 화면의 "직원 추가" (PM 전용, 2026-08-31 추가)
    """
    queryset = User.objects.filter(is_active=True)

    def get_permissions(self):
        # 목록 조회는 로그인한 누구나, 신규 계정 생성은 PM만 — 메서드별로 갈라야 해서
        # permission_classes 클래스 속성 대신 이 훅을 쓴다.
        if self.request.method == 'POST':
            return [IsAdminUserOnly()]
        return [permissions.IsAuthenticated()]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return UserCreateSerializer
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

    @extend_schema(
        tags=['0단계 - 사용자 관리'],
        summary='직원 계정 생성 (PM 전용)',
        description='새 직원 계정을 생성합니다. 비밀번호를 안 보내면 기본값 1111로 생성됩니다.',
        request=UserCreateSerializer,
        responses={201: UserDetailSerializer, 403: OpenApiTypes.OBJECT}
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        # 응답은 화면이 그대로 목록에 얹을 수 있도록 UserDetailSerializer 모양으로 돌려준다
        # (UserCreateSerializer는 write용이라 dept_info 등 *_info 중첩 필드가 없음).
        response = super().create(request, *args, **kwargs)
        user = User.objects.get(pk=response.data['id'])
        response.data = UserDetailSerializer(user).data
        return response


class UserManageView(generics.RetrieveUpdateDestroyAPIView):
    """
    직원 상세 조회/수정/삭제 API (PM 전용, 2026-08-31 추가)
    GET/PATCH/DELETE /api/users/<id>/
    직원관리 화면의 "정보 수정"·"역할 변경"·"계정 상태 변경"·"계정 삭제"가 전부 이 엔드포인트
    하나로 처리된다 — role_code/status_code도 다른 필드와 마찬가지로 그냥 PATCH 바디에 실어
    보내면 되는 일반 필드라 굳이 별도 엔드포인트로 안 쪼갰다.
    """
    queryset = User.objects.all()
    serializer_class = UserDetailSerializer
    permission_classes = [IsAdminUserOnly]

    @extend_schema(tags=['0단계 - 사용자 관리'], summary='직원 상세 조회 (PM 전용)')
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(tags=['0단계 - 사용자 관리'], summary='직원 정보 수정 (PM 전용)',
                    description='이름/부서/직급/직무/권한(role_code)/상태(status_code)/연락처/'
                                '입사일/퇴사일/참여 프로젝트 등을 수정합니다.')
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    @extend_schema(
        tags=['0단계 - 사용자 관리'],
        summary='계정 삭제 (PM 전용)',
        description='실제로는 하드 삭제가 아니라 비활성화 처리합니다. TaskAssignment.assigned_user가 '
                    'on_delete=CASCADE라 진짜로 삭제하면 그 직원이 배정받았던 업무 기록이 전부 함께 '
                    '지워지기 때문입니다 — 대신 is_active=False로 바꾸고 status_code를 RESIGNED로, '
                    'resign_date를 오늘 날짜로 채웁니다. 목록 조회(GET /api/users/)는 is_active=True만 '
                    '보여주므로 화면에서는 즉시 사라집니다.',
        responses={204: None}
    )
    def delete(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.resign_date = timezone.localdate()
        resigned_code = CommonCode.objects.filter(
            group__group_code='USER_STATUS', code_id='RESIGNED'
        ).first()
        if resigned_code:
            instance.status_code = resigned_code
        instance.save()


class UserPasswordResetView(APIView):
    """
    직원 비밀번호 초기화 API (PM 전용, 2026-08-31 추가)
    POST /api/users/<id>/password-reset/
    화면 문구("비밀번호가 1111로 초기화되었습니다")와 맞춰 항상 1111로 고정 초기화한다.
    """
    permission_classes = [IsAdminUserOnly]

    @extend_schema(
        tags=['0단계 - 사용자 관리'],
        summary='비밀번호 초기화 (PM 전용)',
        description='해당 직원의 비밀번호를 1111로 초기화합니다. 다음 로그인 시 본인이 바꿔야 합니다.',
        responses={200: UserPasswordResetResponseSerializer}
    )
    def post(self, request, id):
        try:
            user = User.objects.get(pk=id)
        except User.DoesNotExist:
            return Response({"error": "존재하지 않는 사용자입니다."}, status=status.HTTP_404_NOT_FOUND)
        user.set_password('1111')
        user.save()
        return Response({"message": "비밀번호가 초기화되었습니다."}, status=status.HTTP_200_OK)


class UserImpersonateView(APIView):
    """
    DEV 전용 — 다른 계정으로 재로그인 없이 세션을 바꿔보는 기능 (PM 전용)
    POST /api/users/<id>/impersonate/

    프론트의 DevRoleToggle이 쓰는 API. 2026-08-31에 토큰 저장 위치를 localStorage에서
    HttpOnly 쿠키로 옮기면서, "프론트 JS가 원래 PM 토큰을 변수에 보관해뒀다가 복귀 시
    되돌린다"는 예전 방식이 아예 불가능해졌다(HttpOnly라 JS가 값을 읽을 수 없으므로) —
    대신 서버가 원래 access/refresh 쿠키 값을 dev_original_* 쿠키(이것도 HttpOnly)로
    복사해두고, 복귀는 UserStopImpersonateView가 그 쿠키를 읽어 되돌리는 방식으로 바꿨다.

    settings.DEBUG가 False인 배포(운영)에서는 비밀번호 없이 다른 계정 토큰을 발급하는 게
    되면 안 되므로 항상 403 — 로컬 개발 환경에서만 켜진다.
    """
    permission_classes = [IsAdminUserOnly]

    @extend_schema(
        tags=['0단계 - 사용자 관리'],
        summary='[DEV] 다른 계정으로 세션 미리보기 (PM 전용, DEBUG 환경 한정)',
        description='재로그인 없이 대상 계정의 JWT를 발급받아 쿠키로 바꿔치기합니다. '
                    '운영 배포(DEBUG=False)에서는 항상 403을 반환합니다.',
        responses={200: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT}
    )
    def post(self, request, id):
        if not settings.DEBUG:
            return Response({"error": "이 기능은 개발 환경에서만 사용할 수 있습니다."}, status=status.HTTP_403_FORBIDDEN)
        try:
            target = User.objects.get(pk=id, is_active=True)
        except User.DoesNotExist:
            return Response({"error": "존재하지 않는 사용자입니다."}, status=status.HTTP_404_NOT_FOUND)

        refresh = RefreshToken.for_user(target)
        response = Response({"user": UserSimpleSerializer(target).data}, status=status.HTTP_200_OK)

        # 이미 다른 계정으로 전환 중인 상태에서 또 전환하면(연쇄 전환) dev_original_*을
        # 덮어쓰면 안 된다 — 처음 저장된 "진짜 PM" 토큰이 없어져 버리기 때문. 없을 때만 저장.
        current_access = request.COOKIES.get('access_token')
        current_refresh = request.COOKIES.get('refresh_token')
        if current_access and not request.COOKIES.get('dev_original_access_token'):
            response.set_cookie('dev_original_access_token', current_access, httponly=True,
                                 secure=not settings.DEBUG, samesite='Lax', path='/')
        if current_refresh and not request.COOKIES.get('dev_original_refresh_token'):
            response.set_cookie('dev_original_refresh_token', current_refresh, httponly=True,
                                 secure=not settings.DEBUG, samesite='Lax', path=REFRESH_COOKIE_PATH)

        set_auth_cookies(response, str(refresh.access_token), str(refresh))
        return response


class UserStopImpersonateView(APIView):
    """
    DEV 전용 — impersonate로 바꿔치기했던 세션을 원래 계정(PM)으로 되돌린다.
    POST /api/users/dev-stop-impersonate/
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['0단계 - 사용자 관리'],
        summary='[DEV] 원래 계정으로 복귀',
        description='dev_original_* 쿠키에 저장해둔 원래 access/refresh 토큰으로 되돌립니다.',
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT}
    )
    def post(self, request):
        original_access = request.COOKIES.get('dev_original_access_token')
        original_refresh = request.COOKIES.get('dev_original_refresh_token')
        if not original_access:
            return Response({"error": "되돌아갈 계정 정보가 없습니다."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user_id = RefreshToken(original_refresh).payload.get('user_id') if original_refresh else None
            original_user = User.objects.get(pk=user_id) if user_id else None
        except (TokenError, User.DoesNotExist):
            original_user = None

        response = Response(
            {"user": UserSimpleSerializer(original_user).data if original_user else None},
            status=status.HTTP_200_OK,
        )
        set_auth_cookies(response, original_access, original_refresh)
        response.delete_cookie('dev_original_access_token', path='/')
        response.delete_cookie('dev_original_refresh_token', path=REFRESH_COOKIE_PATH)
        return response
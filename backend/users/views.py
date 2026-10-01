# users/views.py

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
    UserSkillSerializer,
    UserCertificationSerializer,
)
from users.models import UserSkill, UserCertification
from users.permissions import IsAdminUserOnly
from users.jwt_cookies import set_auth_cookies, clear_auth_cookies, REFRESH_COOKIE, REFRESH_COOKIE_PATH
from users.sessions import (
    issue_session_tokens, token_sid_matches, clear_session,
    is_session_active, touch_session, SESSION_IDLE_LIMIT,
)
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


class UploadTokenView(APIView):
    """
    음성 파일처럼 큰 업로드는 Vercel 프록시(요청 본문 4.5MB 제한)를 안 거치고 프론트가
    브라우저에서 백엔드로 직접 보낸다 — 크로스도메인이라 access_token 쿠키가 안 실리므로,
    그 요청에 Authorization 헤더로 실을 토큰 값을 여기서 내려준다(쿠키에 있는 값 그대로,
    HttpOnly라 JS가 직접 못 읽어서 이렇게 한 번 발급해줘야 한다).
    GET /api/users/upload-token/
    """
    @extend_schema(
        tags=['0단계 - 사용자 관리'],
        summary='대용량 업로드용 access 토큰 조회',
        description='로그인 상태의 access_token 쿠키 값을 그대로 반환한다. 백엔드로 직접 파일을 업로드할 때 Authorization 헤더에 실어 쓴다.',
        responses={200: OpenApiTypes.OBJECT}
    )
    def get(self, request):
        raw_token = request.COOKIES.get('access_token')
        if raw_token is None:
            return Response({"detail": "로그인이 필요합니다."}, status=status.HTTP_401_UNAUTHORIZED)
        return Response({"token": raw_token})


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

            # TODO: 데모/개발 편의로 중복 로그인 차단을 임시 해제. 복구하려면 아래 블록의 주석을 풀 것.
            #       (authentication.py 의 sid 검사도 함께 주석 처리돼 있으니 같이 복구)
            # 한 계정당 1개 세션 — 이미 다른 기기에서 로그인 중이면(그 세션이 최근까지
            # 활동 중이면) 이 로그인을 거부한다. 그 세션이 SESSION_IDLE_LIMIT(30분) 넘게
            # 조용했으면 자리를 비운 것으로 보고 통과시켜 새로 발급한다.
            # if is_session_active(user):
            #     mins = int(SESSION_IDLE_LIMIT.total_seconds() // 60)
            #     return Response(
            #         {
            #             "detail": f"이미 다른 기기에서 로그인되어 있습니다. "
            #                       f"기존 기기에서 로그아웃하거나, 활동이 없으면 약 {mins}분 후 다시 시도하세요.",
            #             "code": "already_logged_in",
            #         },
            #         status=status.HTTP_409_CONFLICT,
            #     )

            # 새 세션 발급.
            access, refresh = issue_session_tokens(user, new_session=True)

            response = Response({
                "message": "로그인 성공",
                "user": UserSimpleSerializer(user).data,
            }, status=status.HTTP_200_OK)
            # 2026-08-31: localStorage 대신 HttpOnly 쿠키로 토큰을 내려준다 — localStorage는
            # XSS 한 방이면 JS가 그대로 읽어갈 수 있지만, HttpOnly 쿠키는 JS가 아예 접근할 수
            # 없다. 응답 본문에는 더 이상 access/refresh를 담지 않는다(담으면 결국 프론트가
            # 어딘가에 저장해야 하고, 그게 localStorage면 의미가 없어진다).
            set_auth_cookies(response, access, refresh)
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
        # 활성 세션 표식을 지운다 — 이 계정으로는 어떤 기존 토큰도 더 이상 유효하지 않게 된다.
        if request.user and request.user.is_authenticated:
            clear_session(request.user)
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
        description='refresh_token 쿠키로 새 access 토큰을 발급해 쿠키로 내려줍니다. 활동이 있는 '
                    '동안은 refresh 토큰도 매번 새로 발급해(슬라이딩) 세션이 계속 연장되게 합니다 — '
                    '그렇지 않으면 로그인 시점 기준 24시간 뒤 활동 중이어도 무조건 로그아웃됩니다.',
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

        try:
            user = User.objects.get(pk=refresh.payload.get('user_id'))
        except User.DoesNotExist:
            return Response({"detail": "유효하지 않은 토큰입니다."}, status=status.HTTP_401_UNAUTHORIZED)

        # 한 계정당 1개 세션 — 이 refresh 토큰의 sid가 현재 활성 세션과 다르면(다른 기기에서
        # 새로 로그인함) 재발급을 거부하고 쿠키를 지운다. 프론트는 이 401을 받고 로그인 화면으로.
        if not token_sid_matches(user, refresh):
            resp = Response(
                {"detail": "다른 기기에서 로그인되어 세션이 종료되었습니다.", "code": "session_superseded"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            clear_auth_cookies(resp)
            return resp

        # 이 세션이 살아있음을 기록(유휴 자동해제 방지) + 슬라이딩 재발급.
        touch_session(user)
        # session_key는 그대로 유지한다(new_session=False) — 재발급은 "같은 세션의 연장"이지
        # 새 로그인이 아니므로. refresh 토큰도 새로 발급해 만료를 지금부터 다시 24시간으로 민다.
        access, new_refresh = issue_session_tokens(user, new_session=False)
        response = Response({"detail": "재발급 완료"}, status=status.HTTP_200_OK)
        set_auth_cookies(response, access, new_refresh)
        return response


class CurrentUserProfileView(APIView):
    """
    현재 로그인한 사용자 프로필 조회/수정 API
    GET /api/users/me/
    PATCH /api/users/me/ (본인 프로필 및 온보딩 상태 수정)
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

    @extend_schema(
        tags=['0단계 - 사용자 관리'],
        summary='현재 로그인 유저 프로필 수정 / 온보딩 완료',
        description='본인의 상세 프로필 정보 및 온보딩 완료 상태(`is_onboarded=True`)를 업데이트합니다.',
        request=UserDetailSerializer,
        responses={200: UserDetailSerializer, 400: OpenApiTypes.OBJECT}
    )
    def patch(self, request):
        """
        [2026-09-08 추가] 온보딩 완료 시 프로필(전화번호 등) 입력 및 is_onboarded=True 처리를 함께 수행
        """
        serializer = UserDetailSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==========================================
# 2026-09-16: 본인 기술 스택/자격증 자기관리 API
#
# 지금까지 이 값들(UserSkill/UserCertification)을 추가·삭제하는 API 자체가
# 없었다(UserDetailSerializer는 nested read_only로만 보여줌) — 프로필 화면·
# 직원관리 화면·온보딩 화면 셋 다 "다른 화면에서 관리한다"고 서로 미루기만
# 하고 실제로 저장되는 곳이 없었다(온보딩 화면 주석에 이 사실이 남아있음,
# 실제 확인 결과). 본인이 프로필에서 직접 관리하도록 이 엔드포인트를 새로 만든다.
# ==========================================

class MySkillListCreateView(generics.ListCreateAPIView):
    """
    본인 기술 스택 목록 조회/추가 API
    GET/POST /api/users/me/skills/
    """
    serializer_class = UserSkillSerializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=['0단계 - 사용자 관리'], summary='본인 기술 스택 목록 조회')
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        tags=['0단계 - 사용자 관리'],
        summary='본인 기술 스택 추가',
        description='skill_code(공통코드 SKILL_* 그룹의 code_id)와 proficiency_level(1~5, 생략 시 1)을 받아 추가합니다.',
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def get_queryset(self):
        return self.request.user.skills.select_related('skill_code').all()

    def perform_create(self, serializer):
        # 같은 스킬을 중복으로 추가하면 화면에 똑같은 태그가 두 번 뜨는 것보다,
        # 숙련도만 업데이트하는 게 자연스럽다 — DB에 unique 제약이 없어 그대로 두면
        # 조용히 중복 행이 쌓인다.
        skill_code = serializer.validated_data.get('skill_code')
        existing = self.request.user.skills.filter(skill_code=skill_code).first()
        if existing:
            existing.proficiency_level = serializer.validated_data.get('proficiency_level', existing.proficiency_level)
            existing.save(update_fields=['proficiency_level'])
            serializer.instance = existing
        else:
            serializer.save(user=self.request.user)


class MySkillDetailView(generics.DestroyAPIView):
    """
    본인 기술 스택 삭제 API
    DELETE /api/users/me/skills/<skill_id>/
    조회 대상을 본인 것으로만 한정해서, 남의 skill_id를 넣어도 404로 처리한다(권한 우회 방지).
    """
    serializer_class = UserSkillSerializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=['0단계 - 사용자 관리'], summary='본인 기술 스택 삭제', responses={204: None})
    def delete(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)

    def get_queryset(self):
        return self.request.user.skills.all()


class MyCertificationListCreateView(generics.ListCreateAPIView):
    """
    본인 자격증 목록 조회/추가 API
    GET/POST /api/users/me/certifications/
    """
    serializer_class = UserCertificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=['0단계 - 사용자 관리'], summary='본인 자격증 목록 조회')
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        tags=['0단계 - 사용자 관리'],
        summary='본인 자격증 추가',
        description='cert_code(공통코드 CERTIFICATION_* 그룹의 code_id)와 acquired_date(선택)를 받아 추가합니다.',
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def get_queryset(self):
        return self.request.user.certifications.select_related('cert_code').all()

    def perform_create(self, serializer):
        cert_code = serializer.validated_data.get('cert_code')
        existing = self.request.user.certifications.filter(cert_code=cert_code).first()
        if existing:
            existing.acquired_date = serializer.validated_data.get('acquired_date', existing.acquired_date)
            existing.save(update_fields=['acquired_date'])
            serializer.instance = existing
        else:
            serializer.save(user=self.request.user)


class MyCertificationDetailView(generics.DestroyAPIView):
    """
    본인 자격증 삭제 API
    DELETE /api/users/me/certifications/<cert_id>/
    """
    serializer_class = UserCertificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=['0단계 - 사용자 관리'], summary='본인 자격증 삭제', responses={204: None})
    def delete(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)

    def get_queryset(self):
        return self.request.user.certifications.all()


class ChangePasswordView(APIView):
    """
    본인 비밀번호 변경 API — 지금까지는 PM이 초기화(UserPasswordResetView)해주는 방법만
    있었고, 사용자 본인이 직접 바꾸는 엔드포인트가 없었다.
    PATCH /api/users/me/change-password/
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['0단계 - 사용자 관리'],
        summary='본인 비밀번호 변경',
        description='현재 비밀번호 확인 후 새 비밀번호로 변경합니다. (온보딩 과정에서 변경 시 is_onboarded=True 전환)',
        responses={200: None, 400: None},
    )
    def patch(self, request):
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')

        if not current_password or not new_password:
            return Response({"error": "현재 비밀번호와 새 비밀번호를 모두 입력해주세요."}, status=status.HTTP_400_BAD_REQUEST)
        if not request.user.check_password(current_password):
            return Response({"error": "현재 비밀번호가 올바르지 않습니다."}, status=status.HTTP_400_BAD_REQUEST)
        if len(new_password) < 4:
            return Response({"error": "새 비밀번호는 4자 이상이어야 합니다."}, status=status.HTTP_400_BAD_REQUEST)

        request.user.set_password(new_password)
        
        # 2026-09-08: 초기 비밀번호 변경 시 온보딩을 완료한 것으로 판단하여 is_onboarded=True 함께 반영
        request.user.is_onboarded = True
        request.user.save(update_fields=['password', 'is_onboarded'])
        
        return Response({"message": "비밀번호가 변경되었습니다."}, status=status.HTTP_200_OK)


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

        # UserDetailSerializer가 dept_code/job_role_code/position_code/role_code/status_code(FK 5개)와
        # skills/certifications(역참조 2개)를 매번 물고 있어서, 최적화 없이는 유저 한 명당 쿼리 7개씩
        # 추가로 나간다 — 로컬 SQLite에선 안 느껴졌지만 실제 RDS(원격 MySQL)에 물리면 N+1이 그대로
        # 왕복 지연으로 쌓여서 유저 목록 하나 불러오는 데 30초 넘게 걸리는 게 실측 확인됐다(DEV 롤
        # 토글이 이 API를 호출해서 체감됨). simple=true(UserSimpleSerializer)는 이 FK들을 안 써서
        # 그대로 둬도 되지만, 기본/상세 응답은 항상 이 쿼리셋을 타므로 여기서 한 번에 최적화한다.
        if self.request.query_params.get('simple', None) != 'true':
            queryset = queryset.select_related(
                'dept_code', 'job_role_code', 'position_code', 'role_code', 'status_code',
            ).prefetch_related('skills__skill_code', 'certifications__cert_code')

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
                                '입사일/퇴사일/참여 프로젝트/온보딩 상태 등을 수정합니다.')
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    @extend_schema(
        tags=['0단계 - 사용자 관리'],
        summary='계정 삭제 (PM 전용)',
        description='실제로는 하드 삭제가 아니라 비활성화 처리합니다. TaskAssignment.assigned_user가 '
                    'on_delete=CASCADE라 진짜로 삭제하면 그 직원이 배정받았던 업무 기록이 전부 함께 '
                    '지워지기 때문입니다 — 대신 is_active=False로 바꾸고 status_code를 RESIGNED로, '
                    'resign_date가 비어있으면 오늘 날짜로 채웁니다(이미 있으면 그대로 둠 — 이미 퇴사 '
                    '처리된 계정을 삭제해도 원래 퇴사일이 덮어써지지 않습니다). 목록 조회(GET /api/users/)는 '
                    'is_active=True만 보여주므로 화면에서는 즉시 사라집니다.',
        responses={204: None}
    )
    def delete(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)

    def perform_destroy(self, instance):
        instance.is_active = False
        # 2026-09-16 (사용자 지적): 이미 퇴사 처리(resign_date 있음)된 계정에 "삭제"를
        # 또 누르면, 원래 정확히 기록돼 있던 퇴사일이 삭제 누른 "오늘 날짜"로 조용히
        # 덮어써지는 버그가 있었다 — 퇴사일이 아직 없을 때만 오늘 날짜로 채운다.
        if not instance.resign_date:
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
        description='해당 직원의 비밀번호를 1111로 초기화합니다. 비밀번호 변경 시 온보딩을 새로 진행해야 하므로 is_onboarded=False로 리셋합니다.',
        responses={200: UserPasswordResetResponseSerializer}
    )
    def post(self, request, id):
        try:
            user = User.objects.get(pk=id)
        except User.DoesNotExist:
            return Response({"error": "존재하지 않는 사용자입니다."}, status=status.HTTP_404_NOT_FOUND)
        user.set_password('1111')
        
        # 2026-09-08: PM이 비밀번호를 초기화하면 다시 온보딩 절차를 밟도록 is_onboarded=False로 리셋
        user.is_onboarded = False
        user.save(update_fields=['password', 'is_onboarded'])
        
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

        # DEV 전환도 단일 세션 규칙을 따른다 — target의 session_key를 새로 발급해 sid 검사를
        # 통과시킨다(부수효과: target 계정이 실제로 어딘가 로그인돼 있었다면 그 세션은 끊긴다.
        # DEBUG 전용 도구라 감수).
        access, refresh = issue_session_tokens(target, new_session=True)
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

        set_auth_cookies(response, access, refresh)
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

        # 저장해둔 원본 토큰을 그대로 되돌려주면, 전환해 있던 동안 시간이 흘러 그 토큰(특히
        # refresh, 수명 1일 고정)까지 함께 만료돼 있는 경우가 생긴다 — 그러면 복귀 직후 다음
        # API 호출에서 refresh까지 실패해 실제로 로그아웃당한다(재현됨: DEV 전환을 오래 켜둔 채
        # 왔다갔다 하다 로그아웃). user_id만 꺼내서 그 사람 몫으로 새 토큰을 발급하면 전환해
        # 있던 시간과 무관하게 항상 복귀가 성공한다.
        try:
            user_id = RefreshToken(original_refresh).payload.get('user_id') if original_refresh else None
            original_user = User.objects.get(pk=user_id) if user_id else None
        except (TokenError, User.DoesNotExist):
            original_user = None

        if not original_user:
            return Response({"error": "되돌아갈 계정 정보가 유효하지 않습니다."}, status=status.HTTP_400_BAD_REQUEST)

        # 원래 계정으로 복귀도 새 세션으로 발급한다(전환 동안 만료됐을 수 있는 옛 토큰 대신,
        # 그리고 sid 검사를 통과하도록).
        access, refresh = issue_session_tokens(original_user, new_session=True)
        response = Response(
            {"user": UserSimpleSerializer(original_user).data},
            status=status.HTTP_200_OK,
        )
        set_auth_cookies(response, access, refresh)
        response.delete_cookie('dev_original_access_token', path='/')
        response.delete_cookie('dev_original_refresh_token', path=REFRESH_COOKIE_PATH)
        return response
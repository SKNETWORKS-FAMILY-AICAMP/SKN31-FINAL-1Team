# users/authentication.py
#
# 2026-08-31: JWT를 localStorage 대신 HttpOnly 쿠키로 옮기면서 추가.
# localStorage는 JS가 자유롭게 읽을 수 있어 XSS 한 방이면 토큰이 그대로 털린다 — HttpOnly
# 쿠키는 JS가 아예 못 읽으므로 그 경로를 막는다. 대신 쿠키는 브라우저가 요청마다 "자동으로"
# 실어 보내기 때문에(우리가 헤더에 실을 필요가 없어진 것과 같은 이유로) CSRF에 노출된다 —
# DRF의 기본 JWTAuthentication은 "토큰은 자동으로 안 실린다"는 전제로 CSRF 검사를 안 하는데,
# 쿠키로 옮기면 그 전제가 깨지므로 SessionAuthentication과 동일한 방식으로 직접 CSRF 검증을
# 추가해야 한다.

from django.middleware.csrf import CsrfViewMiddleware
from rest_framework import exceptions
from rest_framework_simplejwt.authentication import JWTAuthentication


class _CsrfCheck(CsrfViewMiddleware):
    def _reject(self, request, reason):
        # 미들웨어의 기본 _reject는 HttpResponse를 반환하는데, 여기서는 그 이유 문자열만
        # 필요하다(DRF SessionAuthentication.enforce_csrf와 동일한 패턴).
        return reason


class CookieJWTAuthentication(JWTAuthentication):
    """
    Authorization 헤더 대신 HttpOnly 쿠키(access_token)에서 JWT를 읽는다.
    """

    def authenticate(self, request):
        raw_token = request.COOKIES.get('access_token')
        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)
        user = self.get_user(validated_token)
        self.enforce_csrf(request)
        return (user, validated_token)

    def enforce_csrf(self, request):
        check = _CsrfCheck(get_response=lambda r: None)
        check.process_request(request)
        reason = check.process_view(request, None, (), {})
        if reason:
            raise exceptions.PermissionDenied('CSRF 검증 실패: %s' % reason)

# users/jwt_cookies.py
#
# access/refresh 토큰을 HttpOnly 쿠키로 내려주고 지우는 로직을 한 곳에 모아둔다 — 로그인/
# 로그아웃/토큰갱신/DEV 계정전환까지 여러 뷰가 같은 쿠키 이름·옵션을 써야 하므로, 흩어져
# 있으면 하나만 고치고 나머지를 빠뜨리기 쉽다.

from django.conf import settings
from rest_framework_simplejwt.settings import api_settings

ACCESS_COOKIE = 'access_token'
REFRESH_COOKIE = 'refresh_token'
# refresh 토큰 쿠키는 필요한 엔드포인트에만 실리도록 경로를 좁힌다 — access 쿠키처럼 모든
# 요청에 매번 실려갈 필요가 없다(재발급/로그아웃/DEV 전환에서만 씀).
REFRESH_COOKIE_PATH = '/api/users/'


def _cookie_kwargs(max_age: int, path: str = '/'):
    return dict(
        httponly=True,
        # 로컬 개발(DEBUG=True, http)에서는 secure=True면 쿠키가 아예 안 실린다 — 배포(https)
        # 에서만 secure를 켠다.
        secure=not settings.DEBUG,
        samesite='Lax',
        max_age=max_age,
        path=path,
    )


def set_auth_cookies(response, access: str, refresh: str | None = None):
    access_lifetime = int(api_settings.ACCESS_TOKEN_LIFETIME.total_seconds())
    response.set_cookie(ACCESS_COOKIE, access, **_cookie_kwargs(access_lifetime, path='/'))
    if refresh is not None:
        refresh_lifetime = int(api_settings.REFRESH_TOKEN_LIFETIME.total_seconds())
        response.set_cookie(REFRESH_COOKIE, refresh, **_cookie_kwargs(refresh_lifetime, path=REFRESH_COOKIE_PATH))


def clear_auth_cookies(response):
    response.delete_cookie(ACCESS_COOKIE, path='/')
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)

# users/sessions.py
#
# 2026-09-07: 한 계정당 동시 로그인 1개만 허용(single active session).
#
# 방식: User.session_key(uuid)를 "현재 유효한 세션"으로 두고, 발급하는 JWT에 sid 클레임으로
# 심는다. 새 기기에서 로그인하면 session_key가 새 값으로 바뀌므로, 이전 기기의 토큰(옛 sid)은
# 다음 요청에서 CookieJWTAuthentication 검사에 걸려 거부된다.
#
# 블랙리스트 앱 없이도 동작한다 — 옛 토큰의 서명·만료는 여전히 유효하지만 sid가 안 맞아서
# 인증을 통과하지 못한다.

import uuid

from rest_framework_simplejwt.tokens import RefreshToken

SID_CLAIM = "sid"


def issue_session_tokens(user, *, new_session: bool) -> tuple[str, str]:
    """
    user 에게 access/refresh 토큰 문자열 한 쌍을 발급한다.

    new_session=True  : 새 세션 시작(로그인·계정전환). session_key 를 새로 만들어 저장 →
                        같은 계정의 다른 기기 세션은 즉시 무효가 된다.
    new_session=False : 기존 세션 유지(토큰 재발급/슬라이딩). 현재 session_key 를 그대로 쓴다.
                        (session_key 가 없으면 이때 만들어 채운다 — 재배포 직후 편입 케이스)
    """
    if new_session or not user.session_key:
        user.session_key = uuid.uuid4().hex
        user.save(update_fields=["session_key"])

    refresh = RefreshToken.for_user(user)
    refresh[SID_CLAIM] = user.session_key
    # access_token 은 refresh 의 커스텀 클레임을 복사해 가므로, sid 를 심은 뒤에 꺼낸다.
    return str(refresh.access_token), str(refresh)


def token_sid_matches(user, token) -> bool:
    """
    토큰의 sid 클레임이 user 의 현재 활성 세션과 일치하는지.

    user.session_key 가 없으면(아직 편입 전) True 로 통과시킨다 — 재배포 시 기존 로그인
    사용자를 한꺼번에 튕기지 않기 위함. 첫 재로그인부터 강제된다.
    """
    current = getattr(user, "session_key", None)
    if not current:
        return True
    try:
        return token.get(SID_CLAIM) == current
    except Exception:
        return False


def clear_session(user) -> None:
    """로그아웃 시 활성 세션 표식을 지운다(어떤 토큰도 유효하지 않게 됨)."""
    if getattr(user, "session_key", None):
        type(user).objects.filter(pk=user.pk).update(session_key=None)

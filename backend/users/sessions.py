# users/sessions.py
#
# 2026-09-07: 한 계정당 동시 로그인 1개만 허용(single active session).
#
# 정책: "먼저 로그인한 세션이 자리를 쥔다".
#   - 이미 활성 세션이 있으면 두 번째 로그인은 차단(409)한다.
#   - 단 그 세션이 SESSION_IDLE_LIMIT 넘게 활동이 없으면 유휴로 보고 자동 해제 → 로그인 허용.
#     (로그아웃 없이 브라우저만 닫아 계정이 영구 잠기는 것을 막기 위함)
#
# 구현: User.session_key(uuid)를 "현재 유효한 세션"으로 두고 JWT에 sid 클레임으로 심는다.
#   session_last_seen 은 그 세션이 마지막으로 인증 요청을 보낸 시각(스로틀링해서 갱신).
#   블랙리스트 앱 없이 동작한다 — 옛 토큰은 서명·만료는 유효하지만 sid가 안 맞아 인증 실패.

import uuid
from datetime import timedelta

from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

SID_CLAIM = "sid"

# 이 시간 넘게 활동이 없는 세션은 "자리 비움"으로 보고 다른 기기 로그인을 허용한다.
SESSION_IDLE_LIMIT = timedelta(minutes=30)

# session_last_seen 을 매 요청마다 쓰면 요청당 UPDATE 1회 → 이 간격 안에서는 갱신을 건너뛴다.
_TOUCH_THROTTLE = timedelta(seconds=60)


def issue_session_tokens(user, *, new_session: bool) -> tuple[str, str]:
    """
    user 에게 access/refresh 토큰 문자열 한 쌍을 발급한다.

    new_session=True  : 새 세션 시작(로그인·계정전환). session_key 를 새로 만들어 저장.
    new_session=False : 기존 세션 유지(토큰 재발급/슬라이딩). 현재 session_key 를 그대로 쓴다.
    """
    if new_session or not user.session_key:
        user.session_key = uuid.uuid4().hex
        user.session_last_seen = timezone.now()
        user.save(update_fields=["session_key", "session_last_seen"])

    refresh = RefreshToken.for_user(user)
    refresh[SID_CLAIM] = user.session_key
    # access_token 은 refresh 의 커스텀 클레임을 복사해 가므로, sid 를 심은 뒤에 꺼낸다.
    return str(refresh.access_token), str(refresh)


def token_sid_matches(user, token) -> bool:
    """
    토큰의 sid 클레임이 user 의 현재 활성 세션과 일치하는지.
    user.session_key 가 없으면(아직 편입 전) True 로 통과 — 재배포 시 기존 로그인 사용자를
    한꺼번에 튕기지 않기 위함. 첫 재로그인부터 강제된다.
    """
    current = getattr(user, "session_key", None)
    if not current:
        return True
    try:
        return token.get(SID_CLAIM) == current
    except Exception:
        return False


def is_session_active(user) -> bool:
    """
    이 계정에 '지금 사용 중인' 세션이 있는지 — 두 번째 로그인을 막을지 판단용.
    session_key 가 있고, 마지막 활동이 SESSION_IDLE_LIMIT 이내면 활성으로 본다.
    """
    if not getattr(user, "session_key", None):
        return False
    last = getattr(user, "session_last_seen", None)
    if last is None:
        return False
    return timezone.now() - last < SESSION_IDLE_LIMIT


def touch_session(user) -> None:
    """활성 세션의 마지막 활동 시각을 갱신(스로틀링). 인증 통과한 요청마다 호출."""
    now = timezone.now()
    last = getattr(user, "session_last_seen", None)
    if last is None or now - last >= _TOUCH_THROTTLE:
        type(user).objects.filter(pk=user.pk).update(session_last_seen=now)
        user.session_last_seen = now


def clear_session(user) -> None:
    """로그아웃 시 활성 세션 표식을 지운다 — 즉시 다른 기기 로그인이 가능해진다."""
    if getattr(user, "session_key", None) or getattr(user, "session_last_seen", None):
        type(user).objects.filter(pk=user.pk).update(session_key=None, session_last_seen=None)

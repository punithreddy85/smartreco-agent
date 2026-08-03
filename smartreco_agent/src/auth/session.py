"""Signed, HttpOnly session cookies. No JWT - there is no cross-service
boundary in this project to justify one (ARCHITECTURE.md \u00a713)."""

from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from smartreco_agent.src.settings import settings

_serializer = URLSafeTimedSerializer(settings.SESSION_SECRET, salt="smartreco-session")


def create_session_value(user_id: str, role: str) -> str:
    return _serializer.dumps({"user_id": user_id, "role": role})


def read_session_value(value: str) -> dict | None:
    try:
        return _serializer.loads(value, max_age=settings.SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None


def set_session_cookie(response, user_id: str, role: str) -> None:
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=create_session_value(user_id, role),
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=settings.APP_BASE_URL.startswith("https://"),
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(settings.SESSION_COOKIE_NAME)

"""FastAPI dependencies for the current user and role checks.

Admin routes are gated by a server-side role dependency checked on every
request; hiding a nav link is not access control (ARCHITECTURE.md \u00a713).
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status

from smartreco_agent.src.auth.session import read_session_value
from smartreco_agent.src.settings import settings


@dataclass(frozen=True)
class CurrentUser:
    id: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def get_current_user(request: Request) -> CurrentUser | None:
    """Read and verify the signed session cookie. Never touches the database -
    ingest and page-render paths stay cheap (ARCHITECTURE.md \u00a71)."""
    raw = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not raw:
        return None
    payload = read_session_value(raw)
    if not payload:
        return None
    return CurrentUser(id=payload["user_id"], role=payload["role"])


def require_user(user: CurrentUser | None = Depends(get_current_user)) -> CurrentUser:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required")
    return user


def require_admin(user: CurrentUser = Depends(require_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user

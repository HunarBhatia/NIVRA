"""Shared dependencies: database session, current user, rate limiting."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.ratelimit import RateLimiter
from app.core.security import hash_token
from app.models import User, UserSession

DB = Annotated[Session, Depends(get_db)]

_settings = get_settings()
auth_limiter = RateLimiter(_settings.auth_rate_limit, _settings.auth_rate_window_seconds)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit_auth(request: Request) -> None:
    if not auth_limiter.allow(client_ip(request)):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Please wait a minute and try again."
        )


def _session_token(request: Request) -> str | None:
    token = request.cookies.get(_settings.session_cookie_name)
    if token:
        return token
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def get_current_user(request: Request, db: DB) -> User:
    token = _session_token(request)
    if token:
        session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
        if session:
            expires = session.expires_at
            if expires > datetime.now(UTC):
                return session.user
            db.delete(session)
            db.commit()
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please open your account first.")


CurrentUser = Annotated[User, Depends(get_current_user)]

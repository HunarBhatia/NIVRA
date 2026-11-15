"""Anonymous accounts (D14): register with a passphrase, log in with Nivra ID + passphrase."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, rate_limit_auth
from app.core.config import get_settings
from app.core.ratelimit import RateLimiter
from app.core.security import (
    hash_passphrase,
    hash_token,
    new_account_code,
    new_session_token,
    normalise_account_code,
    verify_passphrase,
)
from app.models import User, UserSession
from app.schemas import AccountOut, LoginIn, RegisterIn, RegisterOut
from app.services import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


def _start_session(db: DB, response: Response, user: User) -> None:
    token = new_session_token()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours),
        )
    )
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,  # JavaScript can't read it, so XSS can't steal it
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def account_out(user: User) -> AccountOut:
    return AccountOut(
        account_code=user.account_code, has_email=user.email_encrypted is not None,
        created_at=user.created_at,
    )


@router.post("/register", response_model=RegisterOut, status_code=201,
             dependencies=[Depends(rate_limit_auth)])
def register(body: RegisterIn, response: Response, db: DB) -> RegisterOut:
    code = new_account_code()
    while db.scalar(select(User.id).where(User.account_code == code)):
        code = new_account_code()
    user = User(account_code=code, passphrase_hash=hash_passphrase(body.passphrase))
    db.add(user)
    db.flush()
    _start_session(db, response, user)
    audit.record(db, "account.registered", user.id)
    db.commit()
    return RegisterOut(account_code=code)


# Per-account throttle: slows guessing one Nivra ID from many IP addresses.
account_limiter = RateLimiter(settings.login_attempts_per_account_per_hour, 3600)


@router.post("/login", response_model=AccountOut, dependencies=[Depends(rate_limit_auth)])
def login(body: LoginIn, response: Response, db: DB) -> AccountOut:
    code = normalise_account_code(body.account_code)
    if not account_limiter.allow(code):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Too many attempts for this Nivra ID. Please try again later.")
    user = db.scalar(select(User).where(User.account_code == code))
    if not verify_passphrase(user.passphrase_hash if user else None, body.passphrase):
        # Same message whether the ID exists or not.
        if user:
            audit.record(db, "account.login_failed", user.id)
            db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "That Nivra ID and passphrase don't match an account.")
    _start_session(db, response, user)
    audit.record(db, "account.login", user.id)
    db.commit()
    return account_out(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: DB) -> Response:
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
        if session:
            db.delete(session)
            db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=AccountOut)
def me(user: CurrentUser) -> AccountOut:
    return account_out(user)

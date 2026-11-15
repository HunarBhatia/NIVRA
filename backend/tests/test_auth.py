import re

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import auth_limiter
from app.core.db import SessionLocal
from app.models import AuditEvent, User, UserSession
from tests.conftest import PASS, register


def test_register_returns_readable_id_and_logs_in(client: TestClient):
    code = register(client)
    assert re.fullmatch(r"NV-[2-9A-HJ-NP-Z]{4}-[2-9A-HJ-NP-Z]{4}", code)
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["account_code"] == code
    assert me.json()["has_email"] is False


def test_session_cookie_is_httponly(client: TestClient):
    r = client.post("/api/auth/register", json={"passphrase": PASS})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_passphrase_and_token_are_never_stored_in_plain(client: TestClient):
    register(client)
    token = client.cookies.get("nivra_session")
    with SessionLocal() as db:
        user = db.scalar(select(User))
        session = db.scalar(select(UserSession))
    assert PASS not in user.passphrase_hash and user.passphrase_hash.startswith("$argon2")
    assert session.token_hash != token and len(session.token_hash) == 64


def test_short_passphrase_rejected_without_echoing_it(client: TestClient):
    r = client.post("/api/auth/register", json={"passphrase": "short"})
    assert r.status_code == 422
    assert "short" not in r.text


def test_login_with_lowercase_id_works(client: TestClient):
    code = register(client)
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    r = client.post("/api/auth/login", json={"account_code": code.lower(), "passphrase": PASS})
    assert r.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_wrong_passphrase_and_unknown_id_give_same_error(client: TestClient):
    code = register(client)
    client.post("/api/auth/logout")
    wrong = client.post("/api/auth/login", json={"account_code": code, "passphrase": "nope nope"})
    unknown = client.post("/api/auth/login", json={"account_code": "NV-AAAA-AAAA", "passphrase": PASS})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_logout_invalidates_session_server_side(client: TestClient):
    register(client)
    token = client.cookies.get("nivra_session")
    client.post("/api/auth/logout")
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_rate_limit_blocks_repeated_attempts(client: TestClient):
    auth_limiter.limit = 3
    try:
        codes = [client.post("/api/auth/login",
                             json={"account_code": "NV-AAAA-AAAA", "passphrase": "x"}).status_code
                 for _ in range(5)]
    finally:
        auth_limiter.limit = 1000
    assert codes[:3] == [401, 401, 401]
    assert codes[3:] == [429, 429]


def test_optional_email_is_encrypted_and_removable(user_client: TestClient):
    r = user_client.patch("/api/account", json={"email": "someone@example.com"})
    assert r.status_code == 200 and r.json()["has_email"] is True
    with SessionLocal() as db:
        stored = db.scalar(select(User)).email_encrypted
    assert stored and "someone@example.com" not in stored
    r = user_client.patch("/api/account", json={"email": None})
    assert r.json()["has_email"] is False


def test_delete_account_needs_passphrase_and_removes_everything(user_client: TestClient):
    user_client.post("/api/cases", json={"category": "intimate", "urls": ["instagram.com/p/x"]})
    bad = user_client.request("DELETE", "/api/account", json={"passphrase": "wrong one"})
    assert bad.status_code == 403
    ok = user_client.request("DELETE", "/api/account", json={"passphrase": PASS})
    assert ok.status_code == 204
    assert user_client.get("/api/auth/me").status_code == 401
    with SessionLocal() as db:
        assert db.scalar(select(User)) is None
        # Audit rows survive only as anonymous records.
        assert all(e.user_id is None for e in db.scalars(select(AuditEvent)))


def test_security_headers_present(client: TestClient):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cache-control"] == "no-store"

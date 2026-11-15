"""Phase 8: request guards, readiness, login throttling, retention,
agent-state cleanup and production configuration checks."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agents.runtime import get_runtime, reset_runtime
from app.core.config import Settings, get_settings
from app.core.db import SessionLocal
from app.models import AgentRun, AuditEvent, DiscoveryJob, Notification
from app.services.retention import purge
from tests.conftest import PASS, register
from tests.test_agents import case_with_link, draft

EVIL = {"Origin": "https://evil.example"}


@pytest.fixture(autouse=True)
def fresh_runtime():
    reset_runtime(None)
    yield
    reset_runtime(None)


# ---------------- Request guard ----------------

def test_cross_origin_writes_are_blocked(client: TestClient):
    r = client.post("/api/auth/register", json={"passphrase": PASS}, headers=EVIL)
    assert r.status_code == 403
    ok = client.post("/api/auth/register", json={"passphrase": PASS},
                     headers={"Origin": "http://localhost:3000"})
    assert ok.status_code == 201
    # Reads are not origin-checked; no-Origin requests (server-side) pass.
    assert client.get("/api/health", headers=EVIL).status_code == 200


def test_oversized_requests_refused(client: TestClient):
    too_big = str(get_settings().max_request_bytes + 1)
    r = client.post("/api/auth/register", content=b"{}",
                    headers={"Content-Length": too_big, "Content-Type": "application/json"})
    assert r.status_code == 413


def test_every_response_has_a_request_id(client: TestClient):
    r = client.get("/api/health")
    assert len(r.headers["x-request-id"]) == 16
    r = client.get("/api/health", headers={"X-Request-ID": "abc-123"})
    assert r.headers["x-request-id"] == "abc-123"
    r = client.get("/api/health", headers={"X-Request-ID": "<script>"})
    assert r.headers["x-request-id"] != "<script>"


def test_readiness_check(client: TestClient):
    r = client.get("/api/ready")
    assert r.status_code == 200
    assert r.json()["checks"] == {"database": "ok", "evidence_storage": "ok", "platforms": "ok"}


def test_per_account_login_throttle(client: TestClient):
    from app.api import auth
    code = register(client)
    client.post("/api/auth/logout")
    old = auth.account_limiter.limit
    auth.account_limiter.limit = 3
    try:
        codes = [client.post("/api/auth/login", json={"account_code": code, "passphrase": "wrong one"})
                 .status_code for _ in range(4)]
    finally:
        auth.account_limiter.limit = old
        auth.account_limiter.reset()
    assert codes == [401, 401, 401, 429]


# ---------------- Retention ----------------

def test_retention_purges_only_old_operational_records(user_client: TestClient):
    case_id, (link_id,) = case_with_link(user_client)
    run = draft(user_client, case_id, link_id).json()
    user_client.post(f"/api/agents/runs/{run['id']}/decision", json={"decision": "approve"})
    with SessionLocal() as db:
        uid = db.scalar(select(AgentRun.user_id))
        db.add(Notification(user_id=uid, kind="system", title="t", body="b", dedupe_key="x",
                            read_at=datetime.now(UTC)))
        db.add(DiscoveryJob(user_id=uid, provider="user_url", input_url="https://a.test/", status="done"))
        db.commit()
    later = datetime.now(UTC) + timedelta(days=400)
    with SessionLocal() as db:
        out = purge(db, later)
        assert out["audit"] > 0 and out["notifications"] == 1 and out["jobs"] == 1
        assert out["agent_runs"] == 1
        assert db.scalar(select(AuditEvent)) is None and db.scalar(select(AgentRun)) is None
    # The case itself (the user's own record) is untouched.
    assert user_client.get(f"/api/cases/{case_id}").status_code == 200
    # And the run's saved LangGraph state is gone.
    snap = get_runtime().graphs["complaint"].get_state({"configurable": {"thread_id": run["id"]}})
    assert not snap.values


def test_recent_records_are_kept(user_client: TestClient):
    case_with_link(user_client)
    with SessionLocal() as db:
        assert purge(db)["audit"] == 0


def test_account_deletion_forgets_saved_agent_state(user_client: TestClient):
    case_id, (link_id,) = case_with_link(user_client)
    run = draft(user_client, case_id, link_id).json()  # paused, awaiting approval
    graph = get_runtime().graphs["complaint"]
    cfg = {"configurable": {"thread_id": run["id"]}}
    assert graph.get_state(cfg).values  # state saved while waiting
    user_client.request("DELETE", "/api/account", json={"passphrase": PASS})
    assert not graph.get_state(cfg).values


# ---------------- Production configuration ----------------

GOOD = dict(environment="production", database_url="postgresql+psycopg://u:p@db/nivra",
            cookie_secure=True, enable_prototype_tools=False, enable_demo_sites=False, data_key="k" * 44,
            allowed_origins=["https://nivra.example"], agent_checkpoint_path="/data/agents.db",
            evidence_dir="/data/evidence")


@pytest.mark.parametrize("override,message", [
    ({"cookie_secure": False}, "COOKIE_SECURE"),
    ({"enable_prototype_tools": True}, "PROTOTYPE"),
    ({"enable_demo_sites": True}, "DEMO_SITES"),
    ({"email_redirect_to": "me@example.org"}, "REDIRECT"),
    ({"database_url": "sqlite:///x.db"}, "PostgreSQL"),
    ({"discovery_allow_private_hosts": True}, "PRIVATE_HOSTS"),
    ({"data_key": None}, "DATA_KEY"),
    ({"allowed_origins": ["http://nivra.example"]}, "https://"),
    ({"evidence_dir": "./evidence"}, "absolute"),
])
def test_production_refuses_unsafe_settings(monkeypatch, override, message):
    from app.core import config
    values = {**GOOD, **override}
    monkeypatch.setattr(config, "Settings", lambda: Settings(**values))
    config.get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match=message):
            config.get_settings()
    finally:
        monkeypatch.undo()
        config.get_settings.cache_clear()


def test_production_accepts_safe_settings(monkeypatch):
    from app.core import config
    monkeypatch.setattr(config, "Settings", lambda: Settings(**GOOD))
    config.get_settings.cache_clear()
    try:
        assert config.get_settings().is_production
    finally:
        monkeypatch.undo()
        config.get_settings.cache_clear()

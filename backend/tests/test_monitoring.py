"""Phase 7: watched pages, scheduled re-checks, notifications, reminders,
preferences and discreet emails. No real network or email."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import CaseLink, DiscoveryJob, Notification, WatchedPage
from app.services import notify
from app.services.monitoring import deadline_reminders, queue_due_watches
from tests.conftest import PASS, register
from tests.test_discovery import protect, run, site

PAGE = "https://site.test/thread"


@pytest.fixture(autouse=True)
def clear_outbox():
    notify.ConsoleSender.sent.clear()
    yield


def later(hours: float) -> datetime:
    return datetime.now(UTC) + timedelta(hours=hours)


def notes(c: TestClient) -> list[dict]:
    return c.get("/api/notifications").json()


def scheduled_job(now: datetime | None = None) -> str:
    with SessionLocal() as db:
        assert queue_due_watches(db, now or later(1)) == 1
        return db.scalar(select(DiscoveryJob.id).order_by(DiscoveryJob.created_at.desc()))


# ---------------- Watched pages ----------------

def test_watch_crud_and_validation(user_client: TestClient):
    w = user_client.post("/api/watch", json={"url": "site.test/thread"}).json()
    assert w["url"] == PAGE and w["interval_hours"] == 24 and w["enabled"]
    assert user_client.post("/api/watch", json={"url": PAGE, "interval_hours": 1}).status_code == 422
    assert user_client.post("/api/watch", json={"url": "javascript:x"}).status_code == 422
    again = user_client.post("/api/watch", json={"url": PAGE}).json()
    assert again["id"] == w["id"]  # no duplicates
    r = user_client.patch(f"/api/watch/{w['id']}", json={"enabled": False, "interval_hours": 168})
    assert r.json()["enabled"] is False and r.json()["interval_hours"] == 168
    assert user_client.delete(f"/api/watch/{w['id']}").status_code == 204
    assert user_client.get("/api/watch").json() == []


def test_watch_a_case_link(user_client: TestClient):
    case = user_client.post("/api/cases", json={"category": "intimate", "urls": [PAGE]}).json()
    w = user_client.post("/api/watch", json={"link_id": case["links"][0]["id"]}).json()
    assert w["url"] == PAGE and w["link_id"] == case["links"][0]["id"]


def test_watches_are_private(client: TestClient):
    register(client)
    w = client.post("/api/watch", json={"url": PAGE}).json()
    client.post("/api/auth/logout")
    register(client)
    assert client.get("/api/watch").json() == []
    assert client.patch(f"/api/watch/{w['id']}", json={"enabled": False}).status_code == 404
    assert client.delete(f"/api/watch/{w['id']}").status_code == 404


# ---------------- Scheduling ----------------

def test_due_watch_is_queued_once_then_rescheduled(user_client: TestClient):
    protect(user_client)
    user_client.post("/api/watch", json={"url": PAGE})
    now = later(1)
    with SessionLocal() as db:
        assert queue_due_watches(db, now) == 1
        assert queue_due_watches(db, now) == 0  # job already queued / not due again
        w = db.scalar(select(WatchedPage))
        assert abs((w.next_check_at - now) - timedelta(hours=24)) < timedelta(seconds=1)
        assert db.scalar(select(DiscoveryJob.input_url)) == PAGE


def test_nothing_queued_when_paused_or_monitoring_off(user_client: TestClient):
    w = user_client.post("/api/watch", json={"url": PAGE}).json()
    user_client.patch(f"/api/watch/{w['id']}", json={"enabled": False})
    with SessionLocal() as db:
        assert queue_due_watches(db, later(1)) == 0
    user_client.patch(f"/api/watch/{w['id']}", json={"enabled": True})
    user_client.patch("/api/settings/notifications", json={"monitoring_enabled": False})
    with SessionLocal() as db:
        assert queue_due_watches(db, later(1)) == 0


def test_hourly_limit_respected(user_client: TestClient):
    protect(user_client)
    from app.services import monitoring
    old = monitoring.get_settings().discovery_jobs_per_hour
    monitoring.get_settings().discovery_jobs_per_hour = 1
    try:
        user_client.post("/api/discovery/jobs", json={"url": "https://site.test/other"})
        user_client.post("/api/watch", json={"url": PAGE})
        with SessionLocal() as db:
            assert queue_due_watches(db, datetime.now(UTC)) == 0
    finally:
        monitoring.get_settings().discovery_jobs_per_hour = old


# ---------------- Re-check results -> notifications ----------------

def test_scheduled_match_creates_a_notification(user_client: TestClient):
    protect(user_client)
    user_client.post("/api/watch", json={"url": PAGE})
    run(scheduled_job())
    got = notes(user_client)
    assert len(got) == 1 and got[0]["kind"] == "match" and "site.test" in got[0]["title"]
    assert user_client.get("/api/notifications/unread-count").json() == {"unread": 1}


def test_page_that_stops_loading_may_be_removed_never_marked(user_client: TestClient):
    protect(user_client)
    case = user_client.post("/api/cases", json={"category": "intimate", "urls": [PAGE]}).json()
    link_id = case["links"][0]["id"]
    user_client.post(f"/api/links/{link_id}/status", json={"status": "reported"})
    user_client.post("/api/watch", json={"link_id": link_id})
    # The site still exists but the page is gone (404).
    run(scheduled_job(), pages={("site.test", "/other"): httpx.Response(200, text="hi")})
    got = notes(user_client)
    assert got[0]["kind"] == "page_gone" and "may have been removed" in got[0]["body"]
    assert got[0]["href"] == f"/case#{case['id']}"
    with SessionLocal() as db:
        assert db.get(CaseLink, link_id).status == "reported"  # unchanged: user decides


def test_removed_page_that_comes_back_is_flagged(user_client: TestClient):
    protect(user_client)
    case = user_client.post("/api/cases", json={"category": "intimate", "urls": [PAGE]}).json()
    link_id = case["links"][0]["id"]
    for s in ("reported", "removed"):
        user_client.post(f"/api/links/{link_id}/status", json={"status": s})
    user_client.post("/api/watch", json={"link_id": link_id})
    run(scheduled_job(), pages=site())
    assert notes(user_client)[0]["kind"] == "page_back"


def test_user_started_checks_do_not_notify(user_client: TestClient):
    protect(user_client)
    jid = user_client.post("/api/discovery/jobs", json={"url": PAGE}).json()["id"]
    run(jid)
    assert notes(user_client) == []


def test_turned_off_kinds_are_not_created(user_client: TestClient):
    protect(user_client)
    user_client.patch("/api/settings/notifications", json={"notify_matches": False})
    user_client.post("/api/watch", json={"url": PAGE})
    run(scheduled_job())
    assert notes(user_client) == []


# ---------------- Deadline reminders ----------------

def test_deadline_reminders_once_per_day(user_client: TestClient):
    case = user_client.post("/api/cases", json={"category": "intimate", "urls": [PAGE]}).json()
    link_id = case["links"][0]["id"]
    user_client.post(f"/api/links/{link_id}/status", json={"status": "reported"})
    with SessionLocal() as db:
        assert deadline_reminders(db, later(1)) == 0  # too early
        assert deadline_reminders(db, later(20)) == 1  # due soon
        assert deadline_reminders(db, later(21)) == 0  # not repeated
        assert deadline_reminders(db, later(30)) == 1  # overdue
        assert deadline_reminders(db, later(31)) == 0  # once per day
    kinds = [n["title"] for n in notes(user_client)]
    assert any("Deadline passed" in t for t in kinds) and any("Deadline soon" in t for t in kinds)


# ---------------- Notification API ----------------

def test_mark_read_and_privacy(client: TestClient):
    register(client)
    protect(client)
    client.post("/api/watch", json={"url": PAGE})
    run(scheduled_job())
    nid = notes(client)[0]["id"]
    client.post("/api/auth/logout")
    register(client)
    assert notes(client) == []
    assert client.post(f"/api/notifications/{nid}/read").status_code == 404


def test_read_and_read_all(user_client: TestClient):
    case = user_client.post("/api/cases", json={"category": "intimate",
                                                "urls": [PAGE, "https://site.test/b"]}).json()
    for link in case["links"]:
        user_client.post(f"/api/links/{link['id']}/status", json={"status": "reported"})
    with SessionLocal() as db:
        deadline_reminders(db, later(30))
    got = notes(user_client)
    assert len(got) == 2
    user_client.post(f"/api/notifications/{got[0]['id']}/read")
    assert user_client.get("/api/notifications/unread-count").json() == {"unread": 1}
    user_client.post("/api/notifications/read-all")
    assert user_client.get("/api/notifications/unread-count").json() == {"unread": 0}


# ---------------- Preferences and discreet email ----------------

def test_email_mode_needs_an_email(user_client: TestClient):
    assert user_client.patch("/api/settings/notifications", json={"email_mode": "daily"}).status_code == 409
    user_client.patch("/api/account", json={"email": "me@example.com"})
    r = user_client.patch("/api/settings/notifications", json={"email_mode": "daily"})
    assert r.json()["email_mode"] == "daily" and r.json()["has_email"]
    user_client.patch("/api/account", json={"email": None})
    assert user_client.get("/api/settings/notifications").json()["email_mode"] == "off"


def test_immediate_email_is_discreet(user_client: TestClient):
    user_client.patch("/api/account", json={"email": "me@example.com"})
    user_client.patch("/api/settings/notifications", json={"email_mode": "immediate"})
    protect(user_client)
    user_client.post("/api/watch", json={"url": PAGE})
    run(scheduled_job())
    assert len(notify.ConsoleSender.sent) == 1
    to, subject, body = notify.ConsoleSender.sent[0]
    assert to == "me@example.com" and subject == "You have an update from Nivra"
    assert "site.test" not in subject + body and "match" not in (subject + body).lower()


def test_daily_digest_sends_once_a_day(user_client: TestClient):
    user_client.patch("/api/account", json={"email": "me@example.com"})
    user_client.patch("/api/settings/notifications", json={"email_mode": "daily"})
    case = user_client.post("/api/cases", json={"category": "intimate", "urls": [PAGE]}).json()
    user_client.post(f"/api/links/{case['links'][0]['id']}/status", json={"status": "reported"})
    with SessionLocal() as db:
        deadline_reminders(db, later(30))
        assert notify.send_daily_digests(db, later(30)) == 1
        assert notify.send_daily_digests(db, later(31)) == 0
    assert len(notify.ConsoleSender.sent) == 1


def test_account_deletion_removes_monitoring_data(user_client: TestClient):
    protect(user_client)
    user_client.post("/api/watch", json={"url": PAGE})
    run(scheduled_job())
    user_client.request("DELETE", "/api/account", json={"passphrase": PASS})
    with SessionLocal() as db:
        assert db.scalar(select(WatchedPage)) is None
        assert db.scalar(select(Notification)) is None

"""Watched pages, notifications and notification/monitoring settings (section 20)."""

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update

from app.api.cases import _own_link
from app.api.deps import DB, CurrentUser
from app.core.config import get_settings
from app.models import Notification, User, WatchedPage
from app.services import audit, notify
from app.services.links import InvalidUrl, normalise_url

router = APIRouter(prefix="/api", tags=["monitoring"])
settings = get_settings()
NOT_FOUND = "We couldn't find that."
INTERVALS = (12, 24, 72, 168)  # hours: twice a day, daily, every 3 days, weekly
MAX_WATCHES = 50


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WatchIn(Strict):
    url: str | None = Field(default=None, max_length=2048)
    link_id: str | None = Field(default=None, max_length=32)
    interval_hours: int = 24


class WatchUpdateIn(Strict):
    enabled: bool | None = None
    interval_hours: int | None = None


class PrefsIn(Strict):
    monitoring_enabled: bool | None = None
    notify_matches: bool | None = None
    notify_deadlines: bool | None = None
    notify_page_changes: bool | None = None
    email_mode: Literal["off", "immediate", "daily"] | None = None


def _check_interval(hours: int) -> None:
    if hours not in INTERVALS or hours < settings.watch_min_interval_hours:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Choose how often: every 12 hours, daily, every 3 days or weekly.")


def _watch_out(w: WatchedPage) -> dict[str, Any]:
    return {"id": w.id, "url": w.url, "host": w.host, "link_id": w.link_id,
            "interval_hours": w.interval_hours, "enabled": w.enabled,
            "last_checked_at": w.last_checked_at, "next_check_at": w.next_check_at,
            "last_result": w.last_result}


def _own_watch(db: DB, user: User, watch_id: str) -> WatchedPage:
    w = db.scalar(select(WatchedPage).where(WatchedPage.id == watch_id, WatchedPage.user_id == user.id))
    if not w:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return w


# ---------------- Watched pages ----------------

@router.get("/watch")
def list_watches(user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    rows = db.scalars(select(WatchedPage).where(WatchedPage.user_id == user.id)
                      .order_by(WatchedPage.created_at)).all()
    return [_watch_out(w) for w in rows]


@router.post("/watch", status_code=201)
def add_watch(body: WatchIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    """Start watching a page. This is the user's standing approval for Nivra
    to re-check it on the chosen schedule."""
    _check_interval(body.interval_hours)
    link_id = None
    if body.link_id:
        link = _own_link(db, user, body.link_id)
        url, host, link_id = link.url, link.host, link.id
    elif body.url:
        try:
            url, host = normalise_url(body.url)
        except InvalidUrl:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That doesn't look like a web link.") from None
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Give a link to watch.")
    existing = db.scalar(select(WatchedPage).where(WatchedPage.user_id == user.id, WatchedPage.url == url))
    if existing:
        existing.enabled = True
        existing.link_id = existing.link_id or link_id
        db.commit()
        return _watch_out(existing)
    count = db.scalar(select(func.count(WatchedPage.id)).where(WatchedPage.user_id == user.id)) or 0
    if count >= MAX_WATCHES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You're watching the maximum number of pages.")
    w = WatchedPage(user_id=user.id, url=url, host=host, link_id=link_id,
                    interval_hours=body.interval_hours)
    db.add(w)
    db.flush()
    audit.record(db, "monitoring.watch_added", user.id, "watched_page", w.id)
    db.commit()
    return _watch_out(w)


@router.patch("/watch/{watch_id}")
def update_watch(watch_id: str, body: WatchUpdateIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    w = _own_watch(db, user, watch_id)
    if body.interval_hours is not None:
        _check_interval(body.interval_hours)
        w.interval_hours = body.interval_hours
    if body.enabled is not None:
        w.enabled = body.enabled
    db.commit()
    return _watch_out(w)


@router.delete("/watch/{watch_id}", status_code=204)
def delete_watch(watch_id: str, user: CurrentUser, db: DB) -> Response:
    w = _own_watch(db, user, watch_id)
    audit.record(db, "monitoring.watch_removed", user.id, "watched_page", w.id)
    db.delete(w)
    db.commit()
    return Response(status_code=204)


# ---------------- Notifications ----------------

def _note_out(n: Notification) -> dict[str, Any]:
    return {"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "href": n.href,
            "created_at": n.created_at, "read": n.read_at is not None}


@router.get("/notifications")
def list_notifications(user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id)
                      .order_by(Notification.created_at.desc()).limit(50)).all()
    return [_note_out(n) for n in rows]


@router.get("/notifications/unread-count")
def unread_count(user: CurrentUser, db: DB) -> dict[str, int]:
    n = db.scalar(select(func.count(Notification.id)).where(
        Notification.user_id == user.id, Notification.read_at.is_(None))) or 0
    return {"unread": n}


@router.post("/notifications/{note_id}/read")
def mark_read(note_id: str, user: CurrentUser, db: DB) -> dict[str, Any]:
    n = db.scalar(select(Notification).where(Notification.id == note_id, Notification.user_id == user.id))
    if not n:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    n.read_at = n.read_at or datetime.now(UTC)
    db.commit()
    return _note_out(n)


@router.post("/notifications/read-all")
def mark_all_read(user: CurrentUser, db: DB) -> dict[str, int]:
    done = db.execute(update(Notification).where(Notification.user_id == user.id,
                                                 Notification.read_at.is_(None))
                      .values(read_at=datetime.now(UTC))).rowcount
    db.commit()
    return {"marked": done}


# ---------------- Settings ----------------

def _prefs_out(db: DB, user: User) -> dict[str, Any]:
    p = notify.prefs_for(db, user.id)
    return {"monitoring_enabled": p.monitoring_enabled, "notify_matches": p.notify_matches,
            "notify_deadlines": p.notify_deadlines, "notify_page_changes": p.notify_page_changes,
            "email_mode": p.email_mode, "has_email": user.email_encrypted is not None,
            "email_backend": settings.email_backend}


@router.get("/settings/notifications")
def get_prefs(user: CurrentUser, db: DB) -> dict[str, Any]:
    out = _prefs_out(db, user)
    db.commit()
    return out


@router.patch("/settings/notifications")
def update_prefs(body: PrefsIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    p = notify.prefs_for(db, user.id)
    if body.email_mode and body.email_mode != "off" and user.email_encrypted is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Add an email address first.")
    for field in ("monitoring_enabled", "notify_matches", "notify_deadlines",
                  "notify_page_changes", "email_mode"):
        value = getattr(body, field)
        if value is not None:
            setattr(p, field, value)
    audit.record(db, "settings.notifications_updated", user.id)
    db.commit()
    return _prefs_out(db, user)

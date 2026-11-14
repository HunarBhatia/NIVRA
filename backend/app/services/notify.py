"""Creating notifications, and sending the optional discreet emails (20.6).

Emails never contain details: someone else may see the user's inbox, so
the message only says there is an update and to sign in. Delivery is behind
an EmailSender interface: "console" (development: logs that an email WOULD
be sent, without the address) or "smtp" (real delivery, configured by env).
"""

import logging
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decrypt_field
from app.models import Notification, NotificationPrefs, User

log = logging.getLogger("nivra.notify")

KIND_PREF = {"match": "notify_matches", "deadline": "notify_deadlines",
             "page_gone": "notify_page_changes", "page_back": "notify_page_changes"}

EMAIL_SUBJECT = "You have an update from Nivra"
EMAIL_BODY = ("There is an update in your Nivra account.\n\n"
              "For your privacy this email contains no details. Sign in to Nivra to see it.\n\n"
              "You can change or turn off these emails in Settings.")


def prefs_for(db: Session, user_id: str) -> NotificationPrefs:
    p = db.get(NotificationPrefs, user_id)
    if p is None:
        p = NotificationPrefs(user_id=user_id)
        db.add(p)
        db.flush()
    return p


def create(db: Session, user_id: str, *, kind: str, title: str, body: str, href: str,
           dedupe_key: str) -> Notification | None:
    """Adds a notification unless the user turned this kind off or an
    identical one (same dedupe_key) already exists. Commits its own savepoint."""
    prefs = prefs_for(db, user_id)
    pref = KIND_PREF.get(kind)
    if pref and not getattr(prefs, pref):
        return None
    if db.scalar(select(Notification.id).where(Notification.user_id == user_id,
                                               Notification.dedupe_key == dedupe_key)):
        return None
    n = Notification(user_id=user_id, kind=kind, title=title[:160], body=body[:400],
                     href=href[:120], dedupe_key=dedupe_key[:120])
    try:
        with db.begin_nested():
            db.add(n)
    except IntegrityError:  # created concurrently
        return None
    if prefs.email_mode == "immediate":
        send_discreet_email(db, user_id, [n])
    return n


# ---------------- Email ----------------

class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class ConsoleSender:
    """Development: records that an email would be sent (never the address)."""

    sent: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, body: str) -> None:
        ConsoleSender.sent.append((to, subject, body))
        log.info("Email would be sent (console mode)")


class SMTPSender:
    def send(self, to: str, subject: str, body: str) -> None:
        s = get_settings()
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
        msg.set_content(body)
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as server:
            server.starttls()
            if s.smtp_username:
                server.login(s.smtp_username, s.smtp_password or "")
            server.send_message(msg)


def sender() -> EmailSender:
    return SMTPSender() if get_settings().email_backend == "smtp" else ConsoleSender()


def send_discreet_email(db: Session, user_id: str, notes: list[Notification]) -> bool:
    user = db.get(User, user_id)
    to = decrypt_field(user.email_encrypted) if user and user.email_encrypted else None
    if not to or not notes:
        return False
    try:
        sender().send(to, EMAIL_SUBJECT, EMAIL_BODY)
    except Exception as e:  # never let email trouble break the app
        log.error("Email send failed: %s", type(e).__name__)
        return False
    now = datetime.now(UTC)
    for n in notes:
        n.emailed_at = now
    return True


def send_daily_digests(db: Session, now: datetime | None = None) -> int:
    """One discreet email per user per day if they have unread, un-emailed updates."""
    now = now or datetime.now(UTC)
    sent = 0
    for prefs in db.scalars(select(NotificationPrefs).where(NotificationPrefs.email_mode == "daily")):
        if prefs.last_digest_at and now - prefs.last_digest_at < timedelta(hours=24):
            continue
        pending = list(db.scalars(select(Notification).where(
            Notification.user_id == prefs.user_id, Notification.read_at.is_(None),
            Notification.emailed_at.is_(None))))
        if pending and send_discreet_email(db, prefs.user_id, pending):
            prefs.last_digest_at = now
            sent += 1
    db.commit()
    return sent

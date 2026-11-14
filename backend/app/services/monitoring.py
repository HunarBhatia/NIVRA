"""Scheduled monitoring (section 20): re-checking watched pages, reacting to
the results, and deadline reminders. Called by the worker's scheduler tick.

Nivra never decides an outcome from a re-check. A page that stops loading
"may have been removed"; a match that reappears "may be back". The user
checks and records it.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.follow_up import DEADLINE_HOURS, DUE_SOON_HOURS
from app.core.config import get_settings
from app.models import (
    Case,
    CaseLink,
    DiscoveredMatch,
    DiscoveryJob,
    WatchedPage,
)
from app.services import audit, notify


def _day(now: datetime) -> str:
    return now.strftime("%Y-%m-%d")


def queue_due_watches(db: Session, now: datetime | None = None) -> int:
    """Queues a check for every enabled watched page that is due, within each
    user's hourly limit and only while their monitoring is switched on."""
    now = now or datetime.now(UTC)
    s = get_settings()
    queued = 0
    due = db.scalars(select(WatchedPage).where(WatchedPage.enabled.is_(True),
                                               WatchedPage.next_check_at <= now)
                     .order_by(WatchedPage.next_check_at)).all()
    for w in due:
        if queued >= s.scheduled_jobs_per_tick:
            break
        prefs = notify.prefs_for(db, w.user_id)
        if not prefs.monitoring_enabled:
            continue
        busy = db.scalar(select(DiscoveryJob.id).where(
            DiscoveryJob.user_id == w.user_id, DiscoveryJob.input_url == w.url,
            DiscoveryJob.status.in_(("queued", "running"))))
        if busy:
            continue
        last_hour = db.scalar(select(func.count(DiscoveryJob.id)).where(
            DiscoveryJob.user_id == w.user_id,
            DiscoveryJob.created_at > now - timedelta(hours=1))) or 0
        if last_hour >= s.discovery_jobs_per_hour:
            continue  # try again next tick
        job = DiscoveryJob(user_id=w.user_id, provider="user_url", input_url=w.url)
        db.add(job)
        db.flush()
        w.last_job_id = job.id
        w.last_checked_at = now
        w.next_check_at = now + timedelta(hours=w.interval_hours)
        audit.record(db, "monitoring.check_queued", w.user_id, "watched_page", w.id)
        queued += 1
    db.commit()
    return queued


def on_job_finished(db: Session, job: DiscoveryJob) -> None:
    """Turns a finished scheduled check into notifications (if it was one)."""
    watch = db.scalar(select(WatchedPage).where(WatchedPage.last_job_id == job.id))
    if watch is None:
        return
    now = datetime.now(UTC)
    previous = watch.last_result
    watch.last_result = job.status if job.status == "done" else (job.error_code or "failed")
    link = db.get(CaseLink, watch.link_id) if watch.link_id else None
    href = f"/case#{link.case_id}" if link else "/protect"

    if job.status == "failed" and job.error_code in ("not_found", "client_error"):
        notify.create(db, watch.user_id, kind="page_gone",
                      title=f"A watched page on {watch.host} no longer loads",
                      body="It may have been removed. Please check it (or ask someone you trust) "
                           "and record the result in your case.",
                      href=href, dedupe_key=f"gone:{watch.id}:{_day(now)}")
        return
    if job.status != "done":
        return

    new_matches = db.scalar(select(func.count(DiscoveredMatch.id)).where(
        DiscoveredMatch.job_id == job.id, DiscoveredMatch.status == "pending")) or 0
    if link and link.status == "removed" and job.matches_found:
        notify.create(db, watch.user_id, kind="page_back",
                      title=f"A removed page on {watch.host} may be back",
                      body="A re-check found an image that resembles one you protected. Please "
                           "check it; if it's back, mark the link 'back online' and report again.",
                      href=href, dedupe_key=f"back:{watch.id}:{_day(now)}")
    elif new_matches:
        notify.create(db, watch.user_id, kind="match",
                      title=f"Possible match on a watched page ({watch.host})",
                      body=f"{new_matches} possible match(es) to review. Nivra only suggests; "
                           "you decide.",
                      href="/protect", dedupe_key=f"match:{job.id}")
    elif previous in ("not_found", "client_error"):
        notify.create(db, watch.user_id, kind="page_back",
                      title=f"A watched page on {watch.host} loads again",
                      body="It no longer looked removed on the latest check. No matching image was "
                           "found, but you may want to look.",
                      href=href, dedupe_key=f"reload:{watch.id}:{_day(now)}")


def deadline_reminders(db: Session, now: datetime | None = None) -> int:
    """One reminder per reported link when its 24-hour deadline is near and
    one per day once it has passed with no outcome recorded."""
    now = now or datetime.now(UTC)
    made = 0
    rows = db.execute(select(CaseLink, Case).join(Case).where(CaseLink.status == "reported",
                                                              CaseLink.reported_at.is_not(None))).all()
    for link, case in rows:
        hours = (now - link.reported_at).total_seconds() / 3600
        href = f"/case#{case.id}"
        if link.deadline_override or hours >= DEADLINE_HOURS:
            n = notify.create(db, case.user_id, kind="deadline",
                              title=f"Deadline passed for {link.host}",
                              body="No outcome has been recorded since the notice was sent. You "
                                   "can follow up or escalate from your case.",
                              href=href, dedupe_key=f"overdue:{link.id}:{_day(now)}")
        elif hours >= DEADLINE_HOURS - DUE_SOON_HOURS:
            n = notify.create(db, case.user_id, kind="deadline",
                              title=f"Deadline soon for {link.host}",
                              body="The platform's 24-hour deadline is coming up. Check whether "
                                   "they replied and record it in your case.",
                              href=href,
                              dedupe_key=f"duesoon:{link.id}:{link.reported_at.isoformat()}")
        else:
            continue
        made += 1 if n else 0
    db.commit()
    return made


def run_scheduled(db: Session, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    return {"queued": queue_due_watches(db, now), "reminders": deadline_reminders(db, now),
            "digests": notify.send_daily_digests(db, now)}

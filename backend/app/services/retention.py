"""Configurable data retention (section 21.6).

Nivra keeps operational records only as long as they're useful:
- audit events older than NIVRA_RETENTION_AUDIT_DAYS (default 365)
- read updates older than NIVRA_RETENTION_NOTIFICATIONS_DAYS (default 90)
- finished page checks older than NIVRA_RETENTION_JOBS_DAYS (default 180)
  (matches found by them stay; they just lose the job link)
- finished agent runs older than NIVRA_RETENTION_AGENT_RUNS_DAYS (default 180),
  including their saved LangGraph state

Cases, links, complaints, evidence and protected images are the user's own
records: they stay until the user deletes them.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AgentRun, AuditEvent, DiscoveryJob, Notification

log = logging.getLogger("nivra.retention")


def forget_agent_state(run_ids: list[str]) -> None:
    """Deletes saved LangGraph checkpoints for these runs (they can hold
    drafts and case facts)."""
    if not run_ids:
        return
    from app.agents.runtime import LocalRuntime, get_runtime

    runtime = get_runtime()
    if not isinstance(runtime, LocalRuntime):
        return
    for rid in run_ids:
        try:
            runtime.saver.delete_thread(rid)
        except Exception as e:  # never block a deletion on cleanup
            log.error("Checkpoint cleanup failed: %s", type(e).__name__)


def purge(db: Session, now: datetime | None = None) -> dict[str, int]:
    s = get_settings()
    now = now or datetime.now(UTC)
    out = {}
    out["audit"] = db.execute(delete(AuditEvent).where(
        AuditEvent.at < now - timedelta(days=s.retention_audit_days))).rowcount
    out["notifications"] = db.execute(delete(Notification).where(
        Notification.read_at.is_not(None),
        Notification.created_at < now - timedelta(days=s.retention_notifications_days))).rowcount
    out["jobs"] = db.execute(delete(DiscoveryJob).where(
        DiscoveryJob.status.in_(("done", "failed")),
        DiscoveryJob.created_at < now - timedelta(days=s.retention_jobs_days))).rowcount
    old_runs = list(db.scalars(select(AgentRun.id).where(
        AgentRun.status.in_(("completed", "rejected", "failed")),
        AgentRun.updated_at < now - timedelta(days=s.retention_agent_runs_days))))
    if old_runs:
        db.execute(delete(AgentRun).where(AgentRun.id.in_(old_runs)))
    out["agent_runs"] = len(old_runs)
    db.commit()
    forget_agent_state(old_runs)
    return out

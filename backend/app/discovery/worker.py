"""Background worker: runs queued discovery jobs.

Development: started as a thread inside the API (NIVRA_INLINE_WORKER=true).
Production: run separately with  python -m app.discovery.worker
The queue is the discovery_jobs table (D17); Celery/Redis can replace this
module later without changing the API or the job runner.
"""

import logging
import threading
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.discovery.jobs import process_job
from app.models import DiscoveryJob

log = logging.getLogger("nivra.worker")
MAX_ATTEMPTS = 3
STALE_AFTER = timedelta(minutes=10)


def claim_next() -> str | None:
    """Atomically moves the oldest queued job to 'running'. The conditional
    UPDATE means two workers can never claim the same job."""
    with SessionLocal() as db:
        job_id = db.scalar(
            select(DiscoveryJob.id).where(DiscoveryJob.status == "queued")
            .order_by(DiscoveryJob.created_at).limit(1)
        )
        if job_id is None:
            return None
        claimed = db.execute(
            update(DiscoveryJob).where(DiscoveryJob.id == job_id, DiscoveryJob.status == "queued")
            .values(status="running")
        ).rowcount
        db.commit()
        return job_id if claimed == 1 else None


def recover_stale() -> None:
    """Jobs left 'running' by a crashed worker are retried, up to 3 attempts."""
    cutoff = datetime.now(UTC) - STALE_AFTER
    with SessionLocal() as db:
        for job in db.scalars(select(DiscoveryJob).where(DiscoveryJob.status == "running")):
            started = job.started_at
            if started is None or started < cutoff:
                if job.attempts >= MAX_ATTEMPTS:
                    job.status, job.error_code = "failed", "gave_up"
                    job.error_message = "We couldn't finish checking that page."
                else:
                    job.status = "queued"
        db.commit()


def run_once() -> bool:
    job_id = claim_next()
    if job_id is None:
        return False
    with SessionLocal() as db:
        process_job(db, job_id)
    return True


def run_scheduler_tick() -> None:
    """Monitoring (section 20): due re-checks, deadline reminders, digests."""
    from app.services.monitoring import run_scheduled
    with SessionLocal() as db:
        run_scheduled(db)


def run_forever(stop: threading.Event | None = None, poll_seconds: float = 2.0) -> None:
    recover_stale()
    interval = get_settings().scheduler_interval_seconds
    last_tick = 0.0
    while not (stop and stop.is_set()):
        try:
            if time.monotonic() - last_tick >= interval:
                last_tick = time.monotonic()
                run_scheduler_tick()
            if not run_once():
                time.sleep(poll_seconds)
        except Exception as e:  # keep the loop alive; never log job content
            log.error("Worker loop error: %s", type(e).__name__)
            time.sleep(poll_seconds)


def start_inline_worker() -> threading.Event:
    stop = threading.Event()
    threading.Thread(target=run_forever, args=(stop,), daemon=True, name="nivra-worker").start()
    return stop


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    log.info("Nivra discovery worker started")
    run_forever()

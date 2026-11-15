"""Runs one discovery job end to end (deterministic; the Discovery
Coordinator agent in phase 5 will decide WHAT to run, not how)."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.images import thresholds
from app.discovery.fetch import FetchError, SafeFetcher
from app.discovery.matching import compare_all, fingerprint_candidate

from app.discovery.providers import PROVIDERS, DiscoveryProvider, DiscoveryReport
from app.models import DiscoveredMatch, DiscoveryJob
from app.services import audit

log = logging.getLogger("nivra.discovery")


def process_job(
    db: Session,
    job_id: str,
    fetcher: SafeFetcher | None = None,
    providers: dict[str, DiscoveryProvider] | None = None,
) -> DiscoveryJob:
    job = db.get(DiscoveryJob, job_id)
    if job is None:
        raise ValueError("unknown job")
    providers = providers or PROVIDERS
    fetcher = fetcher or SafeFetcher()
    job.status = "running"
    job.stage = "fetching"
    job.scan_log = []
    job.attempts += 1
    job.started_at = datetime.now(UTC)
    db.commit()
    log_entries: list[dict] = []

    report = DiscoveryReport()
    t = thresholds()
    try:
        provider = providers[job.provider]
        for cand in provider.discover(job.input_url, fetcher, report):
            job.stage = "scanning"
            job.candidates_found = report.found
            prints = fingerprint_candidate(cand.data)
            cand.data = b""  # drop the image bytes immediately
            if prints is None:
                report.skipped += 1
                log_entries.append({"i": len(log_entries) + 1, "url": cand.image_url[:300],
                                    "result": "unreadable"})
                job.scan_log = list(log_entries)
                db.commit()
                continue
            job.candidates_checked += 1
            comparisons = compare_all(db, job.user_id, prints, t)
            best = min(comparisons, key=lambda ic: (
                {"exact": 0, "high": 1, "possible": 2, "none": 3}[ic[1].classification],
                ic[1].phash_distance if ic[1].phash_distance is not None else 64), default=None)
            entry = {"i": len(log_entries) + 1, "url": cand.image_url[:300], "phash": prints.phash,
                     "result": best[1].classification if best else "none"}
            if best:
                ph = next((f.value for f in best[0].fingerprints if f.kind == "phash"), None)
                entry.update(distance=best[1].phash_distance, exact=best[1].sha256_equal,
                             label=best[0].label,
                             # Which of the 64 bits differ (the owner's own data).
                             diff=f"{int(ph, 16) ^ int(prints.phash, 16):016x}" if ph else None)
            log_entries.append(entry)
            job.scan_log = list(log_entries)
            hits = [(image, c) for image, c in comparisons if c.classification != "none"]
            for image, c in hits:
                existing = db.scalar(select(DiscoveredMatch).where(
                    DiscoveredMatch.image_id == image.id,
                    DiscoveredMatch.candidate_image_url == cand.image_url))
                if existing:  # seen before: refresh scores, keep the user's review
                    existing.classification = c.classification
                    existing.phash_distance = c.phash_distance
                    existing.sha256_equal = c.sha256_equal
                    existing.job_id = job.id
                    existing.discovered_at = datetime.now(UTC)
                else:
                    db.add(DiscoveredMatch(
                        user_id=job.user_id, job_id=job.id, image_id=image.id,
                        provider=job.provider, source_page_url=cand.source_page_url,
                        candidate_image_url=cand.image_url, classification=c.classification,
                        sha256_equal=c.sha256_equal, phash_distance=c.phash_distance,
                        cosine=c.cosine,
                    ))
                job.matches_found += 1
            db.commit()  # make progress visible to the live scan view
        job.status = "done"
        job.stage = "done"
    except FetchError as e:
        job.status, job.error_code, job.error_message = "failed", e.code, e.message
    except Exception as e:  # never leak details (or URLs) into logs or the UI
        log.error("Discovery job failed with %s", type(e).__name__)
        job.status, job.error_code = "failed", "internal"
        job.error_message = "Something went wrong while checking that page."
    if job.status == "failed":
        job.stage = "failed"
    job.page_title = report.page_title
    job.candidates_found = report.found
    job.candidates_skipped = report.skipped
    job.finished_at = datetime.now(UTC)
    audit.record(db, f"discovery.job_{job.status}", job.user_id, "discovery_job", job.id)
    db.flush()
    # Scheduled re-checks of watched pages turn into notifications (section 20).
    from app.services.monitoring import on_job_finished
    on_job_finished(db, job)
    db.commit()
    return job

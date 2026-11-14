"""Runs one discovery job end to end (deterministic; the Discovery
Coordinator agent in phase 5 will decide WHAT to run, not how)."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.images import thresholds
from app.discovery.fetch import FetchError, SafeFetcher
from app.discovery.matching import fingerprint_candidate, match_candidate
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
    job.attempts += 1
    job.started_at = datetime.now(UTC)
    db.commit()

    report = DiscoveryReport()
    t = thresholds()
    try:
        provider = providers[job.provider]
        for cand in provider.discover(job.input_url, fetcher, report):
            prints = fingerprint_candidate(cand.data)
            cand.data = b""  # drop the image bytes immediately
            if prints is None:
                report.skipped += 1
                continue
            job.candidates_checked += 1
            for image, c in match_candidate(db, job.user_id, prints, t):
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
        job.status = "done"
    except FetchError as e:
        job.status, job.error_code, job.error_message = "failed", e.code, e.message
    except Exception as e:  # never leak details (or URLs) into logs or the UI
        log.error("Discovery job failed with %s", type(e).__name__)
        job.status, job.error_code = "failed", "internal"
        job.error_message = "Something went wrong while checking that page."
    job.page_title = report.page_title
    job.candidates_found = report.found
    job.candidates_skipped = report.skipped
    job.finished_at = datetime.now(UTC)
    audit.record(db, f"discovery.job_{job.status}", job.user_id, "discovery_job", job.id)
    db.commit()
    return job

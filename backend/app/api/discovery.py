"""Discovery jobs and the human review of what they find.

Nothing found by discovery is SENT automatically. Matches from the Protect
page are confirmed by the user before joining a case. A check of a case
link (section 23) lets the assistant DRAFT that link's notice, which still
waits for the user's approval before anything is sent.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select

from app.api.cases import _make_links, _own_case
from app.api.deps import DB, CurrentUser
from app.core.config import get_settings
from app.discovery.fetch import FetchError
from app.models import Case, CaseLink, DiscoveredMatch, DiscoveryJob, ProtectedImage, User
from app.schemas import (
    DiscoveryJobIn,
    DiscoveryJobOut,
    MatchOut,
    MatchReviewIn,
    MatchToCaseIn,
    MatchToCaseOut,
)
from app.services import audit
from app.services.links import InvalidUrl, normalise_url

router = APIRouter(prefix="/api", tags=["discovery"])
settings = get_settings()
NOT_FOUND = "We couldn't find that."


def _match_out(m: DiscoveredMatch) -> MatchOut:
    return MatchOut(
        id=m.id, image_id=m.image_id, image_label=m.image.label, provider=m.provider,
        source_page_url=m.source_page_url, candidate_image_url=m.candidate_image_url,
        classification=m.classification, sha256_equal=m.sha256_equal,
        phash_distance=m.phash_distance, cosine=m.cosine, status=m.status,
        case_link_id=m.case_link_id, discovered_at=m.discovered_at, reviewed_at=m.reviewed_at,
    )


def _own_match(db: DB, user: User, match_id: str) -> DiscoveredMatch:
    m = db.scalar(select(DiscoveredMatch).where(
        DiscoveredMatch.id == match_id, DiscoveredMatch.user_id == user.id))
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return m


@router.post("/discovery/jobs", response_model=DiscoveryJobOut, status_code=202)
def create_job(body: DiscoveryJobIn, user: CurrentUser, db: DB) -> DiscoveryJob:
    try:
        url, _host = normalise_url(body.url)
    except InvalidUrl:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That doesn't look like a web link.") from None
    active = db.scalar(select(func.count(ProtectedImage.id)).where(
        ProtectedImage.user_id == user.id, ProtectedImage.status == "active")) or 0
    if active == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Protect at least one image (and keep it active) before checking pages.")
    hour_ago = datetime.now(UTC) - timedelta(hours=1)
    recent = db.scalar(select(func.count(DiscoveryJob.id)).where(
        DiscoveryJob.user_id == user.id, DiscoveryJob.created_at > hour_ago)) or 0
    if recent >= settings.discovery_jobs_per_hour:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "You've checked a lot of pages this hour. Please try again later.")
    link_id = None
    if body.link_id:
        link = db.scalar(select(CaseLink).join(Case, Case.id == CaseLink.case_id).where(
            CaseLink.id == body.link_id, Case.user_id == user.id))
        if link is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
        link_id = link.id
    job = DiscoveryJob(user_id=user.id, provider="user_url", input_url=url, case_link_id=link_id)
    db.add(job)
    db.flush()
    audit.record(db, "discovery.job_created", user.id, "discovery_job", job.id)
    db.commit()
    return job


@router.get("/demo")
def demo_info() -> dict[str, Any]:
    """The bundled demo sites, if enabled (section 23.2). Public: no user data."""
    if not settings.enable_demo_sites:
        return {"enabled": False, "links": []}
    from app.demo_sites import demo_links
    return {"enabled": True, "photo": "/demo/protected.jpg", "links": demo_links()}


@router.get("/demo/image")
def demo_image(url: str) -> Response:
    """Thumbnail of a bundled demo-site image for the scan view. Only the demo
    sites' own drawn images - real scans never show found images (22.10)."""
    from app.demo_sites import DEMO_SITES, serve_demo
    host = (urlsplit(url).hostname or "").lower()
    if not settings.enable_demo_sites or host not in DEMO_SITES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    try:
        res = serve_demo(url, 5_000_000)
    except FetchError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    if res is None or not res.content_type.startswith("image/"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return Response(res.body, media_type=res.content_type,
                    headers={"Cache-Control": "private, max-age=3600"})


@router.get("/cases/{case_id}/scans")
def case_scans(case_id: str, user: CurrentUser, db: DB) -> dict[str, Any]:
    """The latest check of each link in a case, keyed by link id (section 23.3)."""
    case = db.scalar(select(Case).where(Case.id == case_id, Case.user_id == user.id))
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    link_ids = [lk.id for lk in case.links]
    out: dict[str, Any] = {}
    jobs = db.scalars(select(DiscoveryJob).where(DiscoveryJob.case_link_id.in_(link_ids))
                      .order_by(DiscoveryJob.created_at.desc())) if link_ids else []
    for job in jobs:
        if job.case_link_id in out:
            continue
        best = None
        for e in job.scan_log or []:
            if e.get("result") in ("exact", "high", "possible") and (
                    best is None or (e.get("distance") or 0) < (best.get("distance") or 0)):
                best = e
        out[job.case_link_id] = {
            "job_id": job.id, "status": job.status, "stage": job.stage,
            "images_checked": job.candidates_checked, "matches_found": job.matches_found,
            "best": best["result"] if best else ("none" if job.status == "done" else None),
            "distance": best.get("distance") if best else None,
            "error_message": job.error_message, "finished_at": job.finished_at,
        }
    return out


@router.get("/discovery/jobs", response_model=list[DiscoveryJobOut])
def list_jobs(user: CurrentUser, db: DB) -> list[DiscoveryJob]:
    return list(db.scalars(select(DiscoveryJob).where(DiscoveryJob.user_id == user.id)
                           .order_by(DiscoveryJob.created_at.desc()).limit(20)))


@router.get("/discovery/jobs/{job_id}", response_model=DiscoveryJobOut)
def get_job(job_id: str, user: CurrentUser, db: DB) -> DiscoveryJob:
    job = db.scalar(select(DiscoveryJob).where(DiscoveryJob.id == job_id,
                                               DiscoveryJob.user_id == user.id))
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return job


@router.get("/matches", response_model=list[MatchOut])
def list_matches(user: CurrentUser, db: DB, status_filter: str | None = None) -> list[MatchOut]:
    q = select(DiscoveredMatch).where(DiscoveredMatch.user_id == user.id)
    if status_filter in ("pending", "confirmed", "rejected"):
        q = q.where(DiscoveredMatch.status == status_filter)
    order = {"exact": 0, "high": 1, "possible": 2}
    matches = sorted(db.scalars(q), key=lambda m: (m.status != "pending", order[m.classification],
                                                   -m.discovered_at.timestamp()))
    return [_match_out(m) for m in matches]


@router.post("/matches/{match_id}/review", response_model=MatchOut)
def review_match(match_id: str, body: MatchReviewIn, user: CurrentUser, db: DB) -> MatchOut:
    """The user's decision. Nivra never decides this on its own."""
    m = _own_match(db, user, match_id)
    m.status = body.decision
    m.reviewed_at = None if body.decision == "pending" else datetime.now(UTC)
    audit.record(db, f"match.{body.decision}", user.id, "match", m.id)
    db.commit()
    return _match_out(m)


@router.post("/matches/{match_id}/add-to-case", response_model=MatchToCaseOut)
def add_match_to_case(match_id: str, body: MatchToCaseIn, user: CurrentUser, db: DB) -> MatchToCaseOut:
    m = _own_match(db, user, match_id)
    if m.status != "confirmed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Confirm the match first.")
    if body.case_id:
        case = _own_case(db, user, body.case_id)
    elif body.category:
        case = Case(user_id=user.id, category=body.category)
        db.add(case)
        db.flush()
        audit.record(db, "case.created", user.id, "case", case.id)
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose a case, or what happened.")
    # The page where the image appears is what gets reported.
    made = _make_links(case, [m.source_page_url])
    if made:
        case.links.extend(made)
        db.flush()
        link = made[0]
    else:  # already in this case
        link = next(link for link in case.links if link.url == m.source_page_url)
    m.case_link_id = link.id
    audit.record(db, "match.added_to_case", user.id, "match", m.id)
    db.commit()
    return MatchToCaseOut(case_id=case.id, link_id=link.id)

"""Discovery jobs and the human review of what they find.

Nothing found by discovery is acted on automatically: a match must be
confirmed by the user before it can be added to a case (and only then can a
notice be drafted).
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.cases import _make_links, _own_case
from app.api.deps import DB, CurrentUser
from app.core.config import get_settings
from app.models import Case, DiscoveredMatch, DiscoveryJob, ProtectedImage, User
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
    job = DiscoveryJob(user_id=user.id, provider="user_url", input_url=url)
    db.add(job)
    db.flush()
    audit.record(db, "discovery.job_created", user.id, "discovery_job", job.id)
    db.commit()
    return job


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

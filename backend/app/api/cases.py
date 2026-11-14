"""Cases and links. Every query is scoped to the current user, so one account
can never read or change another's data (a missing or foreign ID is a 404)."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser
from app.core.config import get_settings
from app.models import Case, CaseLink, StatusEvent, User
from app.schemas import (
    CaseCreateIn,
    CaseOut,
    CaseSummaryOut,
    CaseUpdateIn,
    LinkOut,
    LinksAddIn,
    StatusChangeIn,
)
from app.services import audit
from app.services.evidence_store import blob_ids, delete_blobs
from app.services.links import InvalidUrl, can_transition, normalise_url

router = APIRouter(prefix="/api", tags=["cases"])
settings = get_settings()

NOT_FOUND = "We couldn't find that."


def _own_case(db: DB, user: User, case_id: str) -> Case:
    case = db.scalar(select(Case).where(Case.id == case_id, Case.user_id == user.id))
    if not case:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return case


def _own_link(db: DB, user: User, link_id: str) -> CaseLink:
    link = db.scalar(
        select(CaseLink).join(Case).where(CaseLink.id == link_id, Case.user_id == user.id)
    )
    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return link


def _make_links(case: Case, urls: list[str]) -> list[CaseLink]:
    """Validates URLs, skips invalid ones and duplicates already in the case."""
    existing = {link.url for link in case.links}
    made: list[CaseLink] = []
    for raw in urls:
        try:
            url, host = normalise_url(raw)
        except InvalidUrl:
            continue
        if url in existing:
            continue
        existing.add(url)
        link = CaseLink(url=url, host=host, status="found")
        link.events.append(StatusEvent(status="found", note="Link added"))
        made.append(link)
    return made


@router.get("/cases", response_model=list[CaseSummaryOut])
def list_cases(user: CurrentUser, db: DB) -> list[CaseSummaryOut]:
    rows = db.execute(
        select(Case, func.count(CaseLink.id))
        .outerjoin(CaseLink)
        .where(Case.user_id == user.id)
        .group_by(Case.id)
        .order_by(Case.created_at)
    ).all()
    return [
        CaseSummaryOut(id=c.id, category=c.category, created_at=c.created_at, link_count=n)
        for c, n in rows
    ]


@router.post("/cases", response_model=CaseOut, status_code=201)
def create_case(body: CaseCreateIn, user: CurrentUser, db: DB) -> Case:
    count = db.scalar(select(func.count(Case.id)).where(Case.user_id == user.id)) or 0
    if count >= settings.max_cases_per_account:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This account has reached its case limit.")
    case = Case(
        user_id=user.id, category=body.category, self_taken=body.self_taken,
        display_name=body.display_name.strip(),
    )
    case.links.extend(_make_links(case, body.urls))
    db.add(case)
    db.flush()
    audit.record(db, "case.created", user.id, "case", case.id)
    db.commit()
    return case


@router.get("/cases/{case_id}", response_model=CaseOut)
def get_case(case_id: str, user: CurrentUser, db: DB) -> Case:
    return _own_case(db, user, case_id)


@router.patch("/cases/{case_id}", response_model=CaseOut)
def update_case(case_id: str, body: CaseUpdateIn, user: CurrentUser, db: DB) -> Case:
    case = _own_case(db, user, case_id)
    case.display_name = body.display_name.strip()
    db.commit()
    return case


@router.delete("/cases/{case_id}", status_code=204)
def delete_case(case_id: str, user: CurrentUser, db: DB) -> Response:
    case = _own_case(db, user, case_id)
    files = blob_ids(db, case_id=case.id)
    audit.record(db, "case.deleted", user.id, "case", case.id)
    db.delete(case)
    db.commit()
    delete_blobs(files)  # encrypted evidence files on disk
    return Response(status_code=204)


@router.post("/cases/{case_id}/links", response_model=CaseOut)
def add_links(case_id: str, body: LinksAddIn, user: CurrentUser, db: DB) -> Case:
    case = _own_case(db, user, case_id)
    made = _make_links(case, body.urls)
    if not made:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "None of those look like new links.")
    if len(case.links) + len(made) > settings.max_links_per_case:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This case has reached its link limit.")
    case.links.extend(made)
    audit.record(db, "case.links_added", user.id, "case", case.id)
    db.commit()
    return case


@router.post("/links/{link_id}/status", response_model=LinkOut)
def change_status(link_id: str, body: StatusChangeIn, user: CurrentUser, db: DB) -> CaseLink:
    link = _own_link(db, user, link_id)
    if not can_transition(link.status, body.status):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"A link can't go from '{link.status}' to '{body.status}'."
        )
    link.status = body.status
    if body.status == "reported":
        link.reported_at = datetime.now(UTC)
        link.deadline_override = False
    link.events.append(StatusEvent(status=body.status, note=body.note))
    audit.record(db, "link.status_changed", user.id, "link", link.id)
    db.commit()
    return link


@router.post("/links/{link_id}/simulate-deadline", response_model=LinkOut)
def simulate_deadline(link_id: str, user: CurrentUser, db: DB) -> CaseLink:
    """PROTOTYPE ONLY: lets testers pretend the platform's deadline passed.
    Disabled when NIVRA_ENABLE_PROTOTYPE_TOOLS=false (always in production)."""
    if not settings.enable_prototype_tools:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    link = _own_link(db, user, link_id)
    if link.status != "reported":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only reported links have a deadline.")
    link.deadline_override = True
    db.commit()
    return link

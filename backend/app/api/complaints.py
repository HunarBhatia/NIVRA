"""Complaints, case timelines, the account overview and the platform directory."""

from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app import platforms
from app.api.cases import _own_case, _own_link
from app.api.deps import DB, CurrentUser
from app.llm.guardrails import fill
from app.models import (
    AgentRun,
    Case,
    CaseLink,
    Complaint,
    DiscoveredMatch,
    DiscoveryJob,
    EvidenceItem,
    ProtectedImage,
    User,
)
from app.core.config import get_settings
from app.core.security import decrypt_field
from app.services import audit, notify, sending
from app.services import complaints as svc

router = APIRouter(prefix="/api", tags=["complaints"])
NOT_FOUND = "We couldn't find that."


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ComplaintIn(Strict):
    subject: str = Field(min_length=5, max_length=300)
    body: str = Field(min_length=50, max_length=10_000)
    source: Literal["template", "manual"] = "template"


class ComplaintStatusIn(Strict):
    status: Literal["user_approved", "submitted_by_user", "submission_confirmed",
                    "response_received", "resolved", "rejected", "discarded"]
    note: str | None = Field(default=None, max_length=280)
    reference: str | None = Field(default=None, max_length=120)
    channel_kind: Literal["form", "email", "in-app", "other"] | None = None
    channel_label: str | None = Field(default=None, max_length=120)


def _today() -> str:
    return date.today().strftime("%d %B %Y").lstrip("0")


def _complaint_out(db: DB, c: Complaint) -> dict[str, Any]:
    link = db.get(CaseLink, c.link_id)
    case = db.get(Case, c.case_id)
    values = {"URL": link.url if link else "", "NAME": (case.display_name if case else "") or "[Your name]",
              "DATE": _today()}
    p = platforms.get(c.platform_id)
    return {
        "id": c.id, "case_id": c.case_id, "link_id": c.link_id, "status": c.status,
        "status_label": svc.LABEL[c.status], "next_statuses": svc.next_statuses(c),
        "source": c.source, "platform_id": c.platform_id, "platform_name": p["name"] if p else None,
        "subject": c.subject, "body": fill(c.body, values), "reference": c.reference,
        "channel_kind": c.channel_kind, "channel_label": c.channel_label,
        "submitted_at": c.submitted_at, "resolved_at": c.resolved_at, "created_at": c.created_at,
        "events": [{"at": e.at, "status": e.status, "note": e.note} for e in c.events],
    }


def _own_complaint(db: DB, user: User, complaint_id: str) -> Complaint:
    c = db.scalar(select(Complaint).where(Complaint.id == complaint_id, Complaint.user_id == user.id))
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return c


# ---------------- Complaints ----------------

@router.get("/cases/{case_id}/complaints")
def list_complaints(case_id: str, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    case = _own_case(db, user, case_id)
    rows = db.scalars(select(Complaint).where(Complaint.case_id == case.id,
                                              Complaint.status != "discarded")
                      .order_by(Complaint.created_at)).all()
    return [_complaint_out(db, c) for c in rows]


@router.post("/links/{link_id}/complaints", status_code=201)
def create_complaint(link_id: str, body: ComplaintIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    """The user chose this notice text (e.g. Nivra's template) to send."""
    link = _own_link(db, user, link_id)
    c = svc.create(db, user_id=user.id, link=link, subject=body.subject, body=body.body,
                   source=body.source, status="user_approved")
    db.flush()
    audit.record(db, "complaint.created", user.id, "complaint", c.id)
    db.commit()
    return _complaint_out(db, c)


@router.post("/complaints/{complaint_id}/status")
def complaint_status(complaint_id: str, body: ComplaintStatusIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    c = _own_complaint(db, user, complaint_id)
    try:
        svc.transition(db, c, body.status, note=body.note, reference=body.reference,
                       channel_kind=body.channel_kind, channel_label=body.channel_label)
    except svc.ComplaintTransitionError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    audit.record(db, f"complaint.{body.status}", user.id, "complaint", c.id)
    db.commit()
    return _complaint_out(db, c)


# ---------------- Automatic sending (section 22.6) ----------------

SENDS_PER_DAY = 30


@router.get("/links/{link_id}/recipients")
def link_recipients(link_id: str, user: CurrentUser, db: DB) -> dict[str, Any]:
    """Where Nivra would email a notice for this link (shown before sending)."""
    link = _own_link(db, user, link_id)
    return {**sending.recipients_for(link.host), **_sender_details(user)}


def _sender_details(user: User) -> dict[str, Any]:
    """Who a notice is FROM, where replies go, and how it is delivered -
    shown next to every send so the user always knows."""
    s = get_settings()
    reply_to = decrypt_field(user.email_encrypted) if user.email_encrypted else None
    return {"from_address": s.smtp_from, "reply_to": reply_to,
            "delivery": "console" if s.email_backend == "console" else "smtp",
            "redirect_to": s.email_redirect_to}


@router.post("/complaints/{complaint_id}/send")
def send_complaint(complaint_id: str, user: CurrentUser, db: DB) -> dict[str, Any]:
    """Emails an APPROVED complaint to every email channel for its link.
    The user's approval is the go-ahead; nothing is sent before it."""
    c = _own_complaint(db, user, complaint_id)
    if c.status != "user_approved":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Only an approved notice that hasn't been sent can be sent.")
    since = datetime.now(UTC) - timedelta(days=1)
    sent_today = db.scalar(select(func.count(Complaint.id)).where(
        Complaint.user_id == user.id, Complaint.status == "sent_by_nivra",
        Complaint.submitted_at > since)) or 0
    if sent_today >= SENDS_PER_DAY:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "You've sent a lot of notices today. Please try again tomorrow.")
    link = db.get(CaseLink, c.link_id)
    where = sending.recipients_for(link.host)
    from app.demo_sites.scripted import is_scripted_url
    if is_scripted_url(link.url) and get_settings().email_backend == "smtp" \
            and not get_settings().email_redirect_to:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "This link's result is a scripted demo, so Nivra won't email the real "
                            "site. Use development mode or the demo inbox redirect.")
    if where["form_only"]:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"{where['platform']} only accepts reports through its own form, "
                            "so Nivra can't email it. Open the form and paste the notice.")
    if not where["emails"]:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Nivra couldn't find an email contact for this site or its host. "
                            "Look for a contact or abuse page on the site.")
    out = _complaint_out(db, c)  # filled-in subject/body
    reply_to = decrypt_field(user.email_encrypted) if user.email_encrypted else None
    redirect = get_settings().email_redirect_to
    try:
        for r in where["emails"]:
            if redirect:  # demo: deliver to the presenter's inbox, say who it was for
                notify.sender().send(
                    redirect, f"[DEMO for {r['address']}] {out['subject']}",
                    f"Demo redirect: in real use this notice goes to {r['address']}.\n\n{out['body']}",
                    reply_to=reply_to)
            else:
                notify.sender().send(r["address"], out["subject"], out["body"], reply_to=reply_to)
    except Exception:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "The email couldn't be sent. Please try again later.") from None
    to = ", ".join(r["address"] for r in where["emails"])
    dev = get_settings().email_backend == "console"
    svc.transition(db, c, "sent_by_nivra", channel_kind="email", channel_label=to[:120],
                   note=f"Sent by Nivra to {to}" + (
                       " (development: logged, not delivered)" if dev
                       else f" (demo: delivered to {redirect} instead)" if redirect else ""))
    audit.record(db, "complaint.sent_by_nivra", user.id, "complaint", c.id)
    db.commit()
    return {**_complaint_out(db, c), "sent_to": [r["address"] for r in where["emails"]],
            "delivered": not dev, "replies_to_you": bool(reply_to), **_sender_details(user)}


# ---------------- Case timeline ----------------

@router.get("/cases/{case_id}/timeline")
def case_timeline(case_id: str, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    """Everything that happened in a case, newest first: link status changes,
    complaint steps, evidence added (no content), matches added from discovery."""
    case = _own_case(db, user, case_id)
    hosts = {link.id: link.host for link in case.links}
    items: list[dict[str, Any]] = []
    for link in case.links:
        for e in link.events:
            if (e.note or "").startswith("Complaint: "):
                continue  # mirrors a complaint step, which is listed below already
            items.append({"at": e.at, "type": "link", "host": link.host, "link_id": link.id,
                          "status": e.status, "text": e.note or e.status})
    for c in db.scalars(select(Complaint).where(Complaint.case_id == case.id)):
        for e in c.events:
            items.append({"at": e.at, "type": "complaint", "host": hosts.get(c.link_id),
                          "link_id": c.link_id, "status": e.status, "text": f"Complaint: {e.note}"})
    for ev in db.scalars(select(EvidenceItem).where(EvidenceItem.case_id == case.id)):
        items.append({"at": ev.created_at, "type": "evidence", "host": hosts.get(ev.link_id),
                      "link_id": ev.link_id, "status": ev.kind,
                      "text": f"Evidence added ({ev.kind}, encrypted)"})
    for m in db.scalars(select(DiscoveredMatch).where(
            DiscoveredMatch.case_link_id.in_(list(hosts)))):
        items.append({"at": m.reviewed_at or m.discovered_at, "type": "match",
                      "host": hosts.get(m.case_link_id), "link_id": m.case_link_id,
                      "status": m.classification, "text": "Found by Nivra's page check and confirmed by you"})
    items.sort(key=lambda i: i["at"], reverse=True)
    return items


# ---------------- Overview (dashboard) ----------------

@router.get("/overview")
def overview(user: CurrentUser, db: DB) -> dict[str, Any]:
    uid = user.id

    def count(model, *where) -> int:
        return db.scalar(select(func.count()).select_from(model).where(*where)) or 0

    complaint_counts = dict(db.execute(
        select(Complaint.status, func.count()).where(Complaint.user_id == uid)
        .group_by(Complaint.status)).all())
    link_counts = dict(db.execute(
        select(CaseLink.status, func.count()).join(Case).where(Case.user_id == uid)
        .group_by(CaseLink.status)).all())
    cases = db.scalars(select(Case).where(Case.user_id == uid).order_by(Case.created_at)).all()
    return {
        "protected_images": count(ProtectedImage, ProtectedImage.user_id == uid),
        "active_monitoring": count(ProtectedImage, ProtectedImage.user_id == uid,
                                   ProtectedImage.status == "active"),
        "checks_running": count(DiscoveryJob, DiscoveryJob.user_id == uid,
                                DiscoveryJob.status.in_(("queued", "running"))),
        "matches_found": count(DiscoveredMatch, DiscoveredMatch.user_id == uid),
        "matches_to_review": count(DiscoveredMatch, DiscoveredMatch.user_id == uid,
                                   DiscoveredMatch.status == "pending"),
        "confirmed_incidents": len(cases),
        "drafts": complaint_counts.get("draft_generated", 0) + complaint_counts.get("user_approved", 0),
        "submitted": sum(complaint_counts.get(s, 0) for s in
                         ("submitted_by_user", "sent_by_nivra", "submission_confirmed",
                          "response_received", "resolved", "rejected")),
        "pending_responses": complaint_counts.get("submitted_by_user", 0)
        + complaint_counts.get("sent_by_nivra", 0)
        + complaint_counts.get("submission_confirmed", 0),
        "resolved": complaint_counts.get("resolved", 0),
        "links_removed": link_counts.get("removed", 0),
        "approvals_waiting": count(AgentRun, AgentRun.user_id == uid,
                                   AgentRun.status == "awaiting_approval"),
        "cases": [{"id": c.id, "category": c.category, "created_at": c.created_at,
                   "links": len(c.links),
                   "removed": sum(1 for link in c.links if link.status == "removed")} for c in cases],
    }


# ---------------- Platforms ----------------

@router.get("/platforms")
def list_platforms() -> dict[str, Any]:
    data = platforms.load()
    return {"version": data["version"], "note": data["note"], "platforms": data["platforms"]}


@router.get("/platforms/{platform_id}")
def get_platform(platform_id: str) -> dict[str, Any]:
    p = platforms.get(platform_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return p


@router.delete("/complaints/{complaint_id}", status_code=204)
def discard_complaint(complaint_id: str, user: CurrentUser, db: DB) -> Response:
    c = _own_complaint(db, user, complaint_id)
    try:
        svc.transition(db, c, "discarded")
    except svc.ComplaintTransitionError as e:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Only drafts that haven't been sent can be discarded.") from e
    db.commit()
    return Response(status_code=204)



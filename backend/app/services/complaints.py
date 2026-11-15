"""Complaint lifecycle (section 18.5) and how it keeps link statuses in step.

Statuses, in order:
  draft_generated       a draft exists (assistant or template), not approved
  user_approved         the user chose this text to send
  submitted_by_user     the user says they sent it (Nivra cannot see this)
  submission_confirmed  the platform acknowledged it (e.g. a ticket number)
  response_received     the platform replied with a decision or question
  resolved              the content was removed / the matter is closed
  rejected              the platform refused (unresolved)
  discarded             a draft the user dropped

Only the user records submission, confirmation, responses and outcomes.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app import platforms
from app.models import CaseLink, Complaint, ComplaintEvent, StatusEvent
from app.services.links import can_transition

TRANSITIONS: dict[str, set[str]] = {
    "draft_generated": {"user_approved", "discarded"},
    "user_approved": {"submitted_by_user", "sent_by_nivra", "discarded"},
    "submitted_by_user": {"submission_confirmed", "response_received", "resolved", "rejected"},
    # Nivra emailed it after the user's approval (section 22.6).
    "sent_by_nivra": {"submission_confirmed", "response_received", "resolved", "rejected"},
    "submission_confirmed": {"response_received", "resolved", "rejected"},
    "response_received": {"resolved", "rejected"},
    "resolved": set(),
    "rejected": set(),
    "discarded": set(),
}

LABEL = {
    "draft_generated": "Draft generated",
    "user_approved": "Approved by you",
    "submitted_by_user": "Submitted by you",
    "sent_by_nivra": "Sent by Nivra",
    "submission_confirmed": "Submission confirmed",
    "response_received": "Response received",
    "resolved": "Removed / resolved",
    "rejected": "Rejected / unresolved",
    "discarded": "Discarded",
}

# What a complaint step means for the link's own status (blueprint 10.5).
LINK_EFFECT = {"submitted_by_user": "reported", "sent_by_nivra": "reported", "resolved": "removed",
               "rejected": "rejected"}


class ComplaintTransitionError(ValueError):
    pass


def create(db: Session, *, user_id: str, link: CaseLink, subject: str, body: str, source: str,
           status: str, agent_run_id: str | None = None) -> Complaint:
    platform = platforms.resolve(link.host)
    c = Complaint(user_id=user_id, case_id=link.case_id, link_id=link.id,
                  platform_id=platform["id"] if platform else None, status=status, source=source,
                  agent_run_id=agent_run_id, subject=subject[:300], body=body)
    c.events.append(ComplaintEvent(status=status, note=LABEL[status]))
    db.add(c)
    return c


def transition(db: Session, c: Complaint, new: str, *, note: str | None = None,
               reference: str | None = None, channel_kind: str | None = None,
               channel_label: str | None = None) -> Complaint:
    if new not in TRANSITIONS.get(c.status, set()):
        raise ComplaintTransitionError(
            f"A complaint can't go from '{LABEL[c.status]}' to '{LABEL.get(new, new)}'.")
    now = datetime.now(UTC)
    c.status = new
    c.updated_at = now
    if reference:
        c.reference = reference.strip()[:120]
    if channel_kind:
        c.channel_kind, c.channel_label = channel_kind, (channel_label or "")[:120] or None
    if new in ("submitted_by_user", "sent_by_nivra"):
        c.submitted_at = now
    if new in ("resolved", "rejected"):
        c.resolved_at = now
    c.events.append(ComplaintEvent(status=new, note=(note or LABEL[new])[:280]))

    link_status = LINK_EFFECT.get(new)
    if link_status:
        link = db.get(CaseLink, c.link_id)
        if link and can_transition(link.status, link_status):
            link.status = link_status
            if link_status == "reported":
                link.reported_at, link.deadline_override = now, False
            link.events.append(StatusEvent(status=link_status, note=f"Complaint: {LABEL[new]}"))
    return c


def next_statuses(c: Complaint) -> list[str]:
    order = list(LABEL)
    return sorted(TRANSITIONS.get(c.status, set()), key=order.index)

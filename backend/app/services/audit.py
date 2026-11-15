"""Audit trail helper. Never pass content (URLs, emails, text) - only IDs."""

from sqlalchemy.orm import Session

from app.models import AuditEvent


def record(
    db: Session,
    action: str,
    user_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
) -> None:
    db.add(AuditEvent(user_id=user_id, action=action, target_type=target_type, target_id=target_id))

"""Where encrypted evidence files live, and how they are removed.

Database rows cascade on delete, but files on disk don't, so every delete
path (one item, a case, a whole account) calls delete_blobs() after commit.
"""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import EvidenceItem


def blob_path(item_id: str) -> Path:
    # IDs are our own random hex, so they are safe as file names.
    return Path(get_settings().evidence_dir) / f"{item_id}.bin"


def blob_ids(db: Session, *, user_id: str | None = None, case_id: str | None = None) -> list[str]:
    q = select(EvidenceItem.id).where(EvidenceItem.has_blob.is_(True))
    if user_id:
        q = q.where(EvidenceItem.user_id == user_id)
    if case_id:
        q = q.where(EvidenceItem.case_id == case_id)
    return list(db.scalars(q))


def delete_blobs(item_ids: list[str]) -> None:
    for item_id in item_ids:
        try:
            blob_path(item_id).unlink(missing_ok=True)
        except OSError:
            pass

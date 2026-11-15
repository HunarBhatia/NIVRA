"""Evidence locker (section 18.6, decision D9).

Everything is encrypted IN THE BROWSER with a key derived from the user's
passphrase. The server stores ciphertext it cannot read: files go to
NIVRA_EVIDENCE_DIR (never web-served), descriptions are an encrypted blob.
The server only knows each item's kind, size, case and time.
"""

import base64
import binascii
import os
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.api.cases import _own_case, _own_link
from app.api.deps import DB, CurrentUser
from app.core.config import get_settings
from app.models import EvidenceItem, EvidenceLocker, User
from app.services import audit
from app.services.evidence_store import blob_path, delete_blobs

router = APIRouter(prefix="/api", tags=["evidence"])
settings = get_settings()
NOT_FOUND = "We couldn't find that."
B64 = r"^[A-Za-z0-9+/]+={0,2}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LockerIn(Strict):
    salt: str = Field(min_length=16, max_length=64, pattern=B64)
    key_check: str = Field(min_length=24, max_length=500, pattern=B64)


class EvidenceIn(Strict):
    kind: Literal["screenshot", "file", "note", "account", "message"]
    link_id: str | None = Field(default=None, max_length=32)
    enc_meta: str = Field(min_length=24, max_length=20_000, pattern=B64)
    # Encrypted file contents (base64), only for screenshot/file.
    blob: str | None = Field(default=None, max_length=14_000_000)


def _item_out(i: EvidenceItem) -> dict[str, Any]:
    return {"id": i.id, "case_id": i.case_id, "link_id": i.link_id, "kind": i.kind,
            "enc_meta": i.enc_meta, "has_blob": i.has_blob, "size": i.size,
            "created_at": i.created_at}


def _own_item(db: DB, user: User, item_id: str) -> EvidenceItem:
    i = db.scalar(select(EvidenceItem).where(EvidenceItem.id == item_id,
                                             EvidenceItem.user_id == user.id))
    if not i:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return i


@router.get("/evidence/locker")
def get_locker(user: CurrentUser, db: DB) -> dict[str, Any]:
    locker = db.get(EvidenceLocker, user.id)
    if not locker:
        return {"initialized": False}
    return {"initialized": True, "salt": locker.salt, "key_check": locker.key_check, "kdf": locker.kdf}


@router.post("/evidence/locker", status_code=201)
def create_locker(body: LockerIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    if db.get(EvidenceLocker, user.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Your evidence locker is already set up.")
    db.add(EvidenceLocker(user_id=user.id, salt=body.salt, key_check=body.key_check))
    audit.record(db, "evidence.locker_created", user.id)
    db.commit()
    return {"initialized": True}


@router.get("/cases/{case_id}/evidence")
def list_evidence(case_id: str, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    case = _own_case(db, user, case_id)
    rows = db.scalars(select(EvidenceItem).where(EvidenceItem.case_id == case.id)
                      .order_by(EvidenceItem.created_at)).all()
    return [_item_out(i) for i in rows]


@router.post("/cases/{case_id}/evidence", status_code=201)
def add_evidence(case_id: str, body: EvidenceIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    case = _own_case(db, user, case_id)
    if not db.get(EvidenceLocker, user.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Set up your evidence locker first.")
    if body.link_id:
        link = _own_link(db, user, body.link_id)
        if link.case_id != case.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    needs_blob = body.kind in ("screenshot", "file")
    if needs_blob != (body.blob is not None):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Screenshots and files need a file; notes don't.")
    data = b""
    if body.blob is not None:
        try:
            data = base64.b64decode(body.blob, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That file couldn't be read.") from None
        if len(data) > settings.evidence_max_item_bytes:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "That file is too large (max about 7 MB).")
        used = db.scalar(select(func.coalesce(func.sum(EvidenceItem.size), 0))
                         .where(EvidenceItem.user_id == user.id)) or 0
        if used + len(data) > settings.evidence_quota_bytes:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Your evidence locker is full.")
    item = EvidenceItem(user_id=user.id, case_id=case.id, link_id=body.link_id, kind=body.kind,
                        enc_meta=body.enc_meta, has_blob=bool(data), size=len(data))
    db.add(item)
    db.flush()
    if data:
        path = blob_path(item.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Owner-only file permissions where the OS supports them.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
    audit.record(db, "evidence.added", user.id, "evidence", item.id)
    db.commit()
    return _item_out(item)


@router.get("/evidence/{item_id}/blob")
def get_blob(item_id: str, user: CurrentUser, db: DB) -> dict[str, str]:
    item = _own_item(db, user, item_id)
    if not item.has_blob:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    try:
        data = blob_path(item.id).read_bytes()
    except OSError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That file is missing.") from None
    return {"blob": base64.b64encode(data).decode()}


@router.delete("/evidence/{item_id}", status_code=204)
def delete_evidence(item_id: str, user: CurrentUser, db: DB) -> Response:
    item = _own_item(db, user, item_id)
    had_blob = item.has_blob
    audit.record(db, "evidence.deleted", user.id, "evidence", item.id)
    db.delete(item)
    db.commit()
    if had_blob:
        delete_blobs([item_id])
    return Response(status_code=204)

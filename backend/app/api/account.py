"""Account settings and user-controlled deletion."""

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.auth import account_out
from app.api.deps import DB, CurrentUser
from app.core.config import get_settings
from app.core.security import EncryptionUnavailable, encrypt_field, verify_passphrase
from app.models import AgentRun
from app.schemas import AccountDeleteIn, AccountOut, AccountUpdateIn
from app.services import audit, notify
from app.services.evidence_store import blob_ids, delete_blobs
from app.services.retention import forget_agent_state

router = APIRouter(prefix="/api/account", tags=["account"])
settings = get_settings()


@router.patch("", response_model=AccountOut)
def update_account(body: AccountUpdateIn, user: CurrentUser, db: DB) -> AccountOut:
    if "email" in body.model_fields_set:
        if body.email is None:
            user.email_encrypted = None
            notify.prefs_for(db, user.id).email_mode = "off"  # nowhere to send now
            audit.record(db, "account.email_removed", user.id)
        else:
            try:
                user.email_encrypted = encrypt_field(str(body.email))
            except EncryptionUnavailable:
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                    "Email storage isn't set up on this server yet.") from None
            audit.record(db, "account.email_set", user.id)
    db.commit()
    return account_out(user)


@router.delete("", status_code=204)
def delete_account(body: AccountDeleteIn, user: CurrentUser, response: Response, db: DB) -> Response:
    """Deletes the account and everything in it: sessions, cases, links, history.
    Requires the passphrase again so a stolen session can't wipe the account."""
    if not verify_passphrase(user.passphrase_hash, body.passphrase):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That passphrase isn't right.")
    files = blob_ids(db, user_id=user.id)
    runs = list(db.scalars(select(AgentRun.id).where(AgentRun.user_id == user.id)))
    audit.record(db, "account.deleted")  # anonymous: no user id kept
    db.delete(user)
    db.commit()
    delete_blobs(files)  # encrypted evidence files on disk
    forget_agent_state(runs)  # saved LangGraph state for this account's agent runs
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.status_code = 204
    return response

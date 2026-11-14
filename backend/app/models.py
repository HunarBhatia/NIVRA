"""Database tables.

Phase 2: users, sessions, cases, links, status events, audit events.
Phase 3: protected images and their fingerprints (never the images: D13).
Phase 4: discovery jobs and discovered matches (never candidate images: 13.11).
Evidence and complaints are added by later phases
with their own migrations, so each lands with the code that uses it
(PROJECT_DETAILS.txt 13.21).
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.security import new_id


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    """An account. Anonymous by default (D14): just a Nivra ID + passphrase."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    account_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    passphrase_hash: Mapped[str] = mapped_column(String(255))
    email_encrypted: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    cases: Mapped[list["Case"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True,
        order_by="Case.created_at",
    )
    protected_images: Mapped[list["ProtectedImage"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True,
        order_by="ProtectedImage.created_at",
    )


class ProtectedImage(Base):
    """An image the user asked Nivra to watch for. Holds NO image data: only
    a label the user chose, consent records and monitoring status. The
    fingerprints live in `fingerprints` (D13: computed on the device)."""

    __tablename__ = "protected_images"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | paused
    # What the user confirmed, and which wording of the consent text they saw.
    consent_version: Mapped[str] = mapped_column(String(16))
    consented_at: Mapped[datetime] = mapped_column(default=utcnow)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    user: Mapped[User] = relationship(back_populates="protected_images")
    fingerprints: Mapped[list["Fingerprint"]] = relationship(
        back_populates="image", cascade="all, delete-orphan", passive_deletes=True,
    )


class Fingerprint(Base):
    """One fingerprint of a protected image.

    kind = sha256 | phash | embedding; `algorithm` names the exact method
    (e.g. phash-dct-v1, clip-vit-base-patch32-q8) so methods can be replaced
    later without mixing incompatible values. Hashes go in `value`;
    embeddings go in `vector` (JSON now; a pgvector column in production).
    """

    __tablename__ = "fingerprints"
    __table_args__ = (UniqueConstraint("image_id", "kind", name="uq_fingerprint_image_kind"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    image_id: Mapped[str] = mapped_column(
        ForeignKey("protected_images.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    algorithm: Mapped[str] = mapped_column(String(48))
    value: Mapped[str | None] = mapped_column(String(128), default=None, index=True)
    vector: Mapped[list[float] | None] = mapped_column(JSON, default=None)
    dims: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    image: Mapped[ProtectedImage] = relationship(back_populates="fingerprints")


class UserSession(Base):
    """A login session. Only the SHA-256 of the token is stored."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime] = mapped_column()

    user: Mapped[User] = relationship(back_populates="sessions")


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(32))  # intimate | morphed | impersonation
    self_taken: Mapped[bool | None] = mapped_column(Boolean, default=None)
    display_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    user: Mapped[User] = relationship(back_populates="cases")
    links: Mapped[list["CaseLink"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", passive_deletes=True,
        order_by="CaseLink.created_at",
    )


class CaseLink(Base):
    """One URL where the content appears, with its takedown status."""

    __tablename__ = "case_links"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(Text)
    host: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="found")
    reported_at: Mapped[datetime | None] = mapped_column(default=None)
    deadline_override: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    case: Mapped[Case] = relationship(back_populates="links")
    events: Mapped[list["StatusEvent"]] = relationship(
        back_populates="link", cascade="all, delete-orphan", passive_deletes=True,
        order_by="StatusEvent.at",
    )


class StatusEvent(Base):
    """Timeline entry for a link: every status change is kept."""

    __tablename__ = "status_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    link_id: Mapped[str] = mapped_column(ForeignKey("case_links.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(String(280), default=None)
    at: Mapped[datetime] = mapped_column(default=utcnow)

    link: Mapped[CaseLink] = relationship(back_populates="events")


class AuditEvent(Base):
    """Security audit trail. Records WHO did WHAT to WHICH object - never
    content (no URLs, passphrases, emails or notice text)."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_user_at", "user_id", "at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    # Nullable + SET NULL: when a user deletes their account, the audit rows
    # stay as anonymous counts but no longer point to anyone.
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    action: Mapped[str] = mapped_column(String(48))
    target_type: Mapped[str | None] = mapped_column(String(32), default=None)
    target_id: Mapped[str | None] = mapped_column(String(32), default=None)
    at: Mapped[datetime] = mapped_column(default=utcnow)


# ---------- Phase 4: discovery ----------


class DiscoveryJob(Base):
    """One run of a discovery provider for one user, e.g. "check this page".
    Runs in the background (app/discovery/worker.py)."""

    __tablename__ = "discovery_jobs"
    __table_args__ = (Index("ix_discovery_jobs_status_created", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    input_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|running|done|failed
    error_code: Mapped[str | None] = mapped_column(String(32), default=None)
    error_message: Mapped[str | None] = mapped_column(String(255), default=None)
    page_title: Mapped[str | None] = mapped_column(String(200), default=None)
    candidates_found: Mapped[int] = mapped_column(Integer, default=0)
    candidates_checked: Mapped[int] = mapped_column(Integer, default=0)
    candidates_skipped: Mapped[int] = mapped_column(Integer, default=0)
    matches_found: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)


class DiscoveredMatch(Base):
    """A candidate image that resembled one of the user's protected images.

    Stores WHERE it was found and HOW similar it was - never the image.
    Starts as `pending` and needs the user's review (confirmed/rejected)
    before anything can be drafted or sent (human in the loop).
    """

    __tablename__ = "discovered_matches"
    __table_args__ = (
        UniqueConstraint("image_id", "candidate_image_url", name="uq_match_image_candidate"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[str | None] = mapped_column(
        ForeignKey("discovery_jobs.id", ondelete="SET NULL"), default=None
    )
    image_id: Mapped[str] = mapped_column(
        ForeignKey("protected_images.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32))
    source_page_url: Mapped[str] = mapped_column(Text)
    candidate_image_url: Mapped[str] = mapped_column(Text)
    classification: Mapped[str] = mapped_column(String(16))  # exact | high | possible
    sha256_equal: Mapped[bool] = mapped_column(Boolean, default=False)
    phash_distance: Mapped[int | None] = mapped_column(Integer, default=None)
    cosine: Mapped[float | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|confirmed|rejected
    case_link_id: Mapped[str | None] = mapped_column(
        ForeignKey("case_links.id", ondelete="SET NULL"), default=None
    )
    discovered_at: Mapped[datetime] = mapped_column(default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(default=None)

    image: Mapped[ProtectedImage] = relationship()


# ---------- Phase 5: AI agents ----------


class AgentRun(Base):
    """One run of an agent. The paused graph itself lives in the LangGraph
    checkpoint store (thread_id = this id); this row is what the API and the
    audit trail use. `output` holds drafts/plans for the owner only and never
    contains image data; LLM prompts never contain links or names (17.6)."""

    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_user_subject", "user_id", "agent", "subject_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    agent: Mapped[str] = mapped_column(String(24))  # complaint|verification|follow_up|discovery
    subject_type: Mapped[str | None] = mapped_column(String(24), default=None)
    subject_id: Mapped[str | None] = mapped_column(String(32), default=None)
    # running | awaiting_approval | completed | rejected | failed
    status: Mapped[str] = mapped_column(String(20), default="running")
    llm_provider: Mapped[str] = mapped_column(String(16), default="none")
    used_llm: Mapped[bool] = mapped_column(Boolean, default=False)
    output: Mapped[dict | None] = mapped_column(JSON, default=None)
    steps: Mapped[list | None] = mapped_column(JSON, default=None)
    error_code: Mapped[str | None] = mapped_column(String(32), default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)

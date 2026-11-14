"""Validated request/response shapes. Anything not listed here is rejected."""

import math
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

Category = Literal["intimate", "morphed", "impersonation"]
LinkStatus = Literal["found", "reported", "removed", "rejected", "escalated", "reappeared"]

Passphrase = Field(min_length=8, max_length=128)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- Auth / account ----------

class RegisterIn(Strict):
    passphrase: str = Passphrase


class LoginIn(Strict):
    account_code: str = Field(min_length=6, max_length=20)
    passphrase: str = Field(min_length=1, max_length=128)


class AccountOut(BaseModel):
    account_code: str
    has_email: bool
    created_at: datetime


class AccountUpdateIn(Strict):
    # null removes the email; omit to leave it unchanged.
    email: EmailStr | None = None


class AccountDeleteIn(Strict):
    passphrase: str = Field(min_length=1, max_length=128)


# ---------- Cases ----------

class StatusEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    at: datetime
    status: LinkStatus
    note: str | None


class LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    url: str
    host: str
    status: LinkStatus
    reported_at: datetime | None
    deadline_override: bool
    events: list[StatusEventOut]


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    category: Category
    self_taken: bool | None
    display_name: str
    created_at: datetime
    links: list[LinkOut]


class CaseSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    category: Category
    created_at: datetime
    link_count: int


class CaseCreateIn(Strict):
    category: Category
    self_taken: bool | None = None
    display_name: str = Field(default="", max_length=120)
    urls: list[str] = Field(default_factory=list, max_length=50)


class CaseUpdateIn(Strict):
    display_name: str = Field(max_length=120)


class LinksAddIn(Strict):
    urls: list[str] = Field(min_length=1, max_length=50)


class StatusChangeIn(Strict):
    status: LinkStatus
    note: str | None = Field(default=None, max_length=280)


class RegisterOut(BaseModel):
    account_code: str


# ---------- Protected images & fingerprints (phase 3) ----------

Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
PhashHex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{16}$")]

# Bumped whenever the consent wording on the website changes.
CONSENT_VERSION = "2026-11-v1"


class EmbeddingIn(Strict):
    model: str = Field(max_length=48)
    vector: list[float] = Field(min_length=16, max_length=2048)

    @field_validator("vector")
    @classmethod
    def finite(cls, v: list[float]) -> list[float]:
        if not all(math.isfinite(x) for x in v):
            raise ValueError("vector must contain finite numbers")
        return v


class FingerprintsIn(Strict):
    sha256: Sha256Hex
    phash: PhashHex
    phash_algorithm: Literal["phash-dct-v1"] = "phash-dct-v1"
    embedding: EmbeddingIn | None = None


class ConsentIn(Strict):
    """Both must be true. The under-18 route never reaches this API: the
    website sends those users to specialist services instead."""
    subject_is_adult: bool
    is_subject_or_authorised: bool


class ProtectedImageCreateIn(Strict):
    label: str = Field(default="", max_length=80)
    consent: ConsentIn
    consent_version: Literal["2026-11-v1"]
    fingerprints: FingerprintsIn


class ProtectedImageUpdateIn(Strict):
    label: str | None = Field(default=None, max_length=80)
    status: Literal["active", "paused"] | None = None


class FingerprintOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    kind: Literal["sha256", "phash", "embedding"]
    algorithm: str
    created_at: datetime


class ProtectedImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    label: str
    status: Literal["active", "paused"]
    consent_version: str
    created_at: datetime
    fingerprints: list[FingerprintOut]


class MatchCheckIn(Strict):
    """Fingerprints of a copy the user wants checked against THEIR OWN
    protected images (computed in their browser)."""
    sha256: Sha256Hex
    phash: PhashHex
    embedding: EmbeddingIn | None = None


class MatchResultOut(BaseModel):
    image_id: str
    label: str
    classification: Literal["exact", "high", "possible", "none"]
    sha256_equal: bool
    phash_distance: int | None
    cosine: float | None


class MatchCheckOut(BaseModel):
    results: list[MatchResultOut]
    thresholds: dict[str, float]


# ---------- Discovery & matches (phase 4) ----------

class DiscoveryJobIn(Strict):
    url: str = Field(min_length=4, max_length=2048)


class DiscoveryJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    provider: str
    input_url: str
    status: Literal["queued", "running", "done", "failed"]
    error_message: str | None
    page_title: str | None
    candidates_found: int
    candidates_checked: int
    candidates_skipped: int
    matches_found: int
    created_at: datetime
    finished_at: datetime | None


class MatchOut(BaseModel):
    id: str
    image_id: str
    image_label: str
    provider: str
    source_page_url: str
    candidate_image_url: str
    classification: Literal["exact", "high", "possible"]
    sha256_equal: bool
    phash_distance: int | None
    cosine: float | None
    status: Literal["pending", "confirmed", "rejected"]
    case_link_id: str | None
    discovered_at: datetime
    reviewed_at: datetime | None


class MatchReviewIn(Strict):
    decision: Literal["confirmed", "rejected", "pending"]


class MatchToCaseIn(Strict):
    """Either add to an existing case, or create a new one with a category."""
    case_id: str | None = None
    category: Category | None = None


class MatchToCaseOut(BaseModel):
    case_id: str
    link_id: str

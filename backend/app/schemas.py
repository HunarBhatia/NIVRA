"""Validated request/response shapes. Anything not listed here is rejected."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

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

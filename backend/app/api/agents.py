"""AI agent endpoints. Every run is scoped to the logged-in account, and any
consequential step waits for POST /runs/{id}/decision from the user."""

import re
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.agents.common import AgentInputError
from app.agents.service import RunConflict, decide, present, start_run
from app.api.deps import DB, CurrentUser
from app.core.config import get_settings
from app.llm import get_llm
from app.models import AgentRun

router = APIRouter(prefix="/api/agents", tags=["agents"])
settings = get_settings()
RUNS_PER_HOUR = 30
NOT_FOUND = "We couldn't find that."


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ComplaintIn(Strict):
    case_id: str = Field(max_length=32)
    link_id: str = Field(max_length=32)
    platform_name: str | None = Field(default=None, max_length=60)


class VerificationIn(Strict):
    match_id: str = Field(max_length=32)


class DiscoveryIn(Strict):
    urls: list[str] = Field(default_factory=list, max_length=10)


class DecisionIn(Strict):
    decision: Literal["approve", "reject"]
    approved_ids: list[str] | None = Field(default=None, max_length=20)


def _limit(db: DB, user_id: str) -> None:
    since = datetime.now(UTC) - timedelta(hours=1)
    n = db.scalar(select(func.count(AgentRun.id)).where(
        AgentRun.user_id == user_id, AgentRun.created_at > since)) or 0
    if n >= RUNS_PER_HOUR:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "You've used the assistant a lot this hour. Please try again later.")


def _run(db: DB, user, agent: str, state: dict[str, Any], subject_type=None, subject_id=None):
    _limit(db, user.id)
    try:
        run = start_run(db, user, agent, state, subject_type, subject_id)
    except AgentInputError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    return present(db, run)


@router.get("/status")
def agent_status() -> dict[str, Any]:
    llm = get_llm()
    return {"llm_available": llm.available, "llm_provider": llm.name if llm.available else "none",
            "model": llm.model if llm.available else None, "runtime": settings.agent_runtime}


@router.post("/complaint", status_code=201)
def complaint(body: ComplaintIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    # The platform name is only used in the greeting; keep it plain text.
    platform = re.sub(r"[^\w .()&'-]", "", body.platform_name or "")[:60].strip() or None
    return _run(db, user, "complaint",
                {"case_id": body.case_id, "link_id": body.link_id, "platform_name": platform},
                "link", body.link_id)


@router.post("/verification", status_code=201)
def verification(body: VerificationIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    return _run(db, user, "verification", {"match_id": body.match_id}, "match", body.match_id)


@router.post("/follow-up", status_code=201)
def follow_up(user: CurrentUser, db: DB) -> dict[str, Any]:
    return _run(db, user, "follow_up", {})


@router.post("/discovery", status_code=201)
def discovery(body: DiscoveryIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    return _run(db, user, "discovery", {"requested_urls": body.urls})


@router.get("/runs")
def list_runs(user: CurrentUser, db: DB, agent: str | None = None,
              subject_id: str | None = None) -> list[dict[str, Any]]:
    q = select(AgentRun).where(AgentRun.user_id == user.id)
    if agent:
        q = q.where(AgentRun.agent == agent)
    if subject_id:
        q = q.where(AgentRun.subject_id == subject_id)
    runs = db.scalars(q.order_by(AgentRun.created_at.desc()).limit(20)).all()
    return [present(db, r) for r in runs]


def _own_run(db: DB, user, run_id: str) -> AgentRun:
    run = db.scalar(select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user.id))
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return run


@router.get("/runs/{run_id}")
def get_run(run_id: str, user: CurrentUser, db: DB) -> dict[str, Any]:
    return present(db, _own_run(db, user, run_id))


@router.post("/runs/{run_id}/decision")
def run_decision(run_id: str, body: DecisionIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    run = _own_run(db, user, run_id)
    try:
        run = decide(db, run, body.model_dump())
    except RunConflict as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    return present(db, run)

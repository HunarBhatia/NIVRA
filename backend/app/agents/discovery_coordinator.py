"""Agent 1: Discovery Coordinator (section 17.8).

gather -> plan -> approval (PAUSE if anything to check) -> enqueue

Decides WHICH pages to check, within the user's limits, and queues the jobs
the matching engine then runs. Pure rules - no LLM: these decisions must
be predictable and explainable. Because checking pages means Nivra visiting
third-party sites, the plan is shown to the user before anything is queued.
"""

from datetime import UTC, datetime, timedelta
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from sqlalchemy import func, select

from app.agents.common import step
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import Case, CaseLink, DiscoveredMatch, DiscoveryJob, ProtectedImage
from app.services import audit
from app.services.links import InvalidUrl, normalise_url

NAME = "discovery"
RECENT = timedelta(hours=24)
MAX_PLAN = 10


class State(TypedDict, total=False):
    user_id: str
    now: float
    requested_urls: list[str]
    active_images: int
    quota_left: int
    candidates: list[dict]
    recent_urls: list[str]
    plan: list[dict]
    skipped: list[dict]
    message: str
    job_ids: list[str]
    steps: list[dict]


def gather(state: State) -> State:
    now = datetime.fromtimestamp(state["now"], UTC)
    s = get_settings()
    uid = state["user_id"]
    with SessionLocal() as db:
        active = db.scalar(select(func.count(ProtectedImage.id)).where(
            ProtectedImage.user_id == uid, ProtectedImage.status == "active")) or 0
        last_hour = db.scalar(select(func.count(DiscoveryJob.id)).where(
            DiscoveryJob.user_id == uid, DiscoveryJob.created_at > now - timedelta(hours=1))) or 0
        recent = db.scalars(select(DiscoveryJob.input_url).where(
            DiscoveryJob.user_id == uid,
            (DiscoveryJob.created_at > now - RECENT) | DiscoveryJob.status.in_(("queued", "running")))).all()
        confirmed_pages = db.scalars(select(DiscoveredMatch.source_page_url).where(
            DiscoveredMatch.user_id == uid, DiscoveredMatch.status == "confirmed")).all()
        removed_links = db.scalars(select(CaseLink.url).join(Case).where(
            Case.user_id == uid, CaseLink.status == "removed")).all()
    candidates = []
    for raw in state.get("requested_urls", []):
        try:
            candidates.append({"url": normalise_url(raw)[0], "reason": "You asked to check this page.",
                               "source": "requested"})
        except InvalidUrl:
            candidates.append({"url": raw[:200], "reason": "invalid", "source": "invalid"})
    candidates += [{"url": u, "reason": "Re-check a page where you confirmed a match.",
                    "source": "confirmed_match"} for u in confirmed_pages]
    candidates += [{"url": u, "reason": "This was removed; check it hasn't come back.",
                    "source": "removed_link"} for u in removed_links]
    return {"active_images": active, "quota_left": max(0, s.discovery_jobs_per_hour - last_hour),
            "candidates": candidates, "recent_urls": list(set(recent)),
            "steps": step(state, "gather", note=str(len(candidates)))}


def plan(state: State) -> State:
    if state["active_images"] == 0:
        return {"plan": [], "skipped": [], "message": "Protect at least one image (and keep it "
                "active) before checking pages.", "steps": step(state, "plan", note="no_images")}
    recent = set(state["recent_urls"])
    seen: set[str] = set()
    planned, skipped = [], []
    limit = min(MAX_PLAN, state["quota_left"])
    for c in state["candidates"]:
        url = c["url"]
        if c["source"] == "invalid":
            skipped.append({**c, "why": "That doesn't look like a web link."})
        elif url in seen:
            continue
        elif url in recent:
            skipped.append({**c, "why": "Already checked in the last 24 hours (or in progress)."})
        elif len(planned) >= limit:
            skipped.append({**c, "why": "Over this hour's limit; try again later."})
        else:
            planned.append({**c, "id": f"p{len(planned) + 1}"})
        seen.add(url)
    msg = f"{len(planned)} page(s) ready to check." if planned else "Nothing new to check right now."
    return {"plan": planned, "skipped": skipped, "message": msg,
            "steps": step(state, "plan", note=str(len(planned)))}


def approval(state: State) -> State:
    if not state["plan"]:
        return {"plan": [], "steps": step(state, "approval", note="nothing_to_approve")}
    decision = interrupt({"kind": "discovery_plan", "plan": state["plan"],
                          "skipped": state["skipped"], "message": state["message"]})
    chosen: list[dict] = []
    if isinstance(decision, dict) and decision.get("decision") == "approve":
        ids = decision.get("approved_ids")
        chosen = [p for p in state["plan"] if ids is None or p["id"] in set(ids)]
    return {"plan": chosen, "steps": step(state, "approval", note=str(len(chosen)))}


def enqueue(state: State) -> State:
    if not state["plan"]:
        return {"job_ids": [], "steps": step(state, "enqueue", note="0")}
    ids = []
    with SessionLocal() as db:
        for p in state["plan"]:
            job = DiscoveryJob(user_id=state["user_id"], provider="user_url", input_url=p["url"])
            db.add(job)
            db.flush()
            audit.record(db, "discovery.job_created", state["user_id"], "discovery_job", job.id)
            ids.append(job.id)
        db.commit()
    return {"job_ids": ids, "steps": step(state, "enqueue", note=str(len(ids)))}


def build_graph() -> StateGraph:
    g = StateGraph(State)
    g.add_node("gather", gather)
    g.add_node("plan", plan)
    g.add_node("approval", approval)
    g.add_node("enqueue", enqueue)
    g.add_edge(START, "gather")
    g.add_edge("gather", "plan")
    g.add_edge("plan", "approval")
    g.add_edge("approval", "enqueue")
    g.add_edge("enqueue", END)
    return g

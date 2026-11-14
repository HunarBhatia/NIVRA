"""Starting, resuming and presenting agent runs (used by app/api/agents.py)."""

import logging
import time
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.agents.common import AgentInputError
from app.agents.runtime import get_runtime
from app.agents.verification_assistant import DISCLAIMER
from app.llm import get_llm
from app.llm.guardrails import fill
from app.models import AgentRun, Case, CaseLink, User
from app.services import audit

log = logging.getLogger("nivra.agents")


class RunConflict(Exception):
    pass


def _today() -> str:
    return date.today().strftime("%d %B %Y").lstrip("0")


def _finish(db: Session, run: AgentRun, result: dict[str, Any]) -> AgentRun:
    state, payload = result["state"], result.get("interrupt")
    run.steps = state.get("steps")
    run.used_llm = state.get("source") == "llm" or any(
        d.get("source") == "llm" for d in state.get("drafts", []) or [])
    if payload is not None:
        run.status = "awaiting_approval"
        run.output = payload
    else:
        if run.agent == "complaint":
            run.status = "completed" if state.get("status") == "approved" else "rejected"
            run.output = {"draft": state.get("draft"), "source": state.get("source"),
                          "approved": state.get("status") == "approved"}
        elif run.agent == "verification":
            run.status = "completed"
            run.output = {k: state.get(k) for k in
                          ("classification", "summary", "facts", "missing_evidence", "next_step",
                           "source")}
            run.output["disclaimer"] = DISCLAIMER
        elif run.agent == "follow_up":
            run.status = "completed"
            run.output = {"reminders": state.get("reminders", []),
                          "drafts": [d for d in state.get("drafts", [])
                                     if d["id"] in set(state.get("approved_ids", []))],
                          "applied": state.get("applied", 0)}
        else:  # discovery
            run.status = "completed"
            run.output = {"job_ids": state.get("job_ids", []), "message": state.get("message"),
                          "skipped": state.get("skipped", [])}
    run.updated_at = datetime.now(UTC)
    audit.record(db, f"agent.{run.agent}.{run.status}", run.user_id, "agent_run", run.id)
    db.commit()
    return run


def start_run(db: Session, user: User, agent: str, state: dict[str, Any],
              subject_type: str | None = None, subject_id: str | None = None) -> AgentRun:
    llm = get_llm()
    run = AgentRun(user_id=user.id, agent=agent, subject_type=subject_type, subject_id=subject_id,
                   llm_provider=llm.name if llm.available else "none")
    db.add(run)
    db.commit()
    try:
        result = get_runtime().start(agent, run.id, {"user_id": user.id, "now": time.time(), **state})
    except AgentInputError:
        db.delete(run)
        db.commit()
        raise
    except Exception as e:  # agent crashed: record it, never leak details
        log.error("Agent %s failed with %s", agent, type(e).__name__)
        run.status, run.error_code = "failed", type(e).__name__[:32]
        run.updated_at = datetime.now(UTC)
        db.commit()
        return run
    return _finish(db, run, result)


def decide(db: Session, run: AgentRun, decision: dict[str, Any]) -> AgentRun:
    if run.status != "awaiting_approval":
        raise RunConflict("This run isn't waiting for a decision.")
    try:
        result = get_runtime().resume(run.agent, run.id, decision)
    except Exception as e:
        log.error("Agent %s resume failed with %s", run.agent, type(e).__name__)
        run.status, run.error_code = "failed", type(e).__name__[:32]
        db.commit()
        return run
    return _finish(db, run, result)


def present(db: Session, run: AgentRun) -> dict[str, Any]:
    """API view of a run. Complaint/follow-up drafts are shown with the real
    link, name and date filled in - for the owner's eyes only."""
    out = run.output or {}
    view = {"id": run.id, "agent": run.agent, "status": run.status, "subject_id": run.subject_id,
            "used_llm": run.used_llm, "llm_provider": run.llm_provider,
            "error_code": run.error_code, "created_at": run.created_at, "output": out}
    if run.agent == "complaint" and out.get("draft") and run.subject_id:
        link = db.get(CaseLink, run.subject_id)
        case = link and db.get(Case, link.case_id)
        if link and case and case.user_id == run.user_id:
            values = {"URL": link.url, "NAME": case.display_name or "[Your name]", "DATE": _today()}
            view["preview"] = {"subject": out["draft"]["subject"],
                               "body": fill(out["draft"]["body"], values)}
    if run.agent == "follow_up" and out.get("drafts"):
        previews = []
        for d in out["drafts"]:
            link = db.get(CaseLink, d["link_id"])
            case = link and db.get(Case, link.case_id)
            if not (link and case and case.user_id == run.user_id):
                continue
            sent = d.get("sent_at")
            values = {"URL": link.url, "NAME": case.display_name or "[Your name]", "DATE": _today(),
                      "SENT_DATE": datetime.fromisoformat(sent).strftime("%d %B %Y") if sent else "[date sent]"}
            previews.append({"id": d["id"], "link_id": d["link_id"], "kind": d["kind"],
                             "source": d["source"], "subject": d["draft"]["subject"],
                             "body": fill(d["draft"]["body"], values)})
        view["previews"] = previews
    return view

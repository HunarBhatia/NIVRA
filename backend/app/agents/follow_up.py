"""Agent 4: Follow-up (section 17.11).

scan -> drafts -> approval (PAUSE if there are drafts) -> apply

- scan is deterministic: deadlines come from the recorded status history
  and the 24-hour rule. It never assumes a notice was received, acted on or
  resolved - "no reply recorded" is reported as exactly that.
- drafts: follow-up/escalation messages for overdue or refused links
  (LLM optional, placeholders only, guardrails, template fallback).
- approval: the user picks which drafts to keep; apply then notes it on the
  link's timeline. Sending is still the user's own action.
"""

from datetime import UTC, datetime, timedelta
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from sqlalchemy import select

from app.agents.common import llm_validated, step
from app.agents.legal import allowed_citations, grounds_for
from app.core.db import SessionLocal
from app.llm import get_llm
from app.llm.guardrails import check_draft
from app.models import Case, CaseLink, StatusEvent

NAME = "follow_up"
DEADLINE_HOURS = 24
DUE_SOON_HOURS = 6
QUIET_HOURS = 72
MAX_DRAFTS = 5

SYSTEM = (
    "You draft short, firm follow-up messages about takedown requests that were not answered or "
    "were refused, addressed to a platform's Grievance Officer in India. Plain English, polite, "
    "no threats, no new legal claims beyond the grounds given. Use {{URL}} for the link, {{NAME}} "
    "for the sender, {{DATE}} for today's date and {{SENT_DATE}} for when the first notice was "
    "sent. Never write a real link, name or date."
)
SCHEMA = {
    "type": "object",
    "properties": {"subject": {"type": "string"}, "body": {"type": "string"}},
    "required": ["subject", "body"],
    "additionalProperties": False,
}


class State(TypedDict, total=False):
    user_id: str
    now: float  # fixed at start so a resumed run sees the same clock
    reminders: list[dict]
    drafts: list[dict]
    approved_ids: list[str]
    applied: int
    steps: list[dict]


def _hours(since: datetime, now: datetime) -> float:
    return (now - since).total_seconds() / 3600


def scan(state: State) -> State:
    now = datetime.fromtimestamp(state["now"], UTC)
    reminders = []
    with SessionLocal() as db:
        rows = db.execute(select(CaseLink, Case).join(Case).where(Case.user_id == state["user_id"])).all()
        for link, case in rows:
            base = {"link_id": link.id, "case_id": case.id, "host": link.host,
                    "category": case.category, "self_taken": case.self_taken}
            if link.status == "reported" and link.reported_at:
                hrs = _hours(link.reported_at, now)
                due_at = link.reported_at + timedelta(hours=DEADLINE_HOURS)
                if link.deadline_override or hrs >= DEADLINE_HOURS:
                    kind = "no_reply_recorded" if hrs >= QUIET_HOURS else "overdue"
                    reminders.append({**base, "kind": kind, "hours_since_sent": round(hrs, 1),
                                      "sent_at": link.reported_at.isoformat(),
                                      "message": "The 24-hour deadline has passed and no reply has "
                                                 "been recorded. Follow up or escalate."})
                elif hrs >= DEADLINE_HOURS - DUE_SOON_HOURS:
                    reminders.append({**base, "kind": "due_soon", "due_at": due_at.isoformat(),
                                      "message": "The platform's 24-hour deadline is coming up. "
                                                 "Check whether they replied."})
            elif link.status == "rejected":
                reminders.append({**base, "kind": "refused",
                                  "sent_at": link.reported_at.isoformat() if link.reported_at else None,
                                  "message": "The platform refused. You can escalate to the "
                                             "Grievance Appellate Committee or the police."})
            elif link.status == "reappeared":
                reminders.append({**base, "kind": "reappeared",
                                  "message": "The content came back. Report it again."})
    return {"reminders": reminders, "steps": step(state, "scan", note=str(len(reminders)))}


def _template(kind: str, platform: str) -> dict:
    if kind == "refused":
        body = (f"To the Grievance Officer, {platform},\n\nOn {{{{SENT_DATE}}}} I asked you to remove "
                "content at {{URL}} under Rule 3(2)(b) of the Information Technology (Intermediary "
                "Guidelines and Digital Media Ethics Code) Rules, 2021. My request was refused.\n\n"
                "I ask you to review this decision and remove the content. If it is not removed, "
                "I intend to appeal to the Grievance Appellate Committee and report the matter to "
                "the police.\n\nRegards,\n{{NAME}}\nDate: {{DATE}}")
        subject = "Request to review refused removal (IT Rules 2021, Rule 3(2)(b))"
    else:
        body = (f"To the Grievance Officer, {platform},\n\nOn {{{{SENT_DATE}}}} I asked you to remove "
                "content at {{URL}} under Rule 3(2)(b) of the Information Technology (Intermediary "
                "Guidelines and Digital Media Ethics Code) Rules, 2021, which requires removal within "
                "24 hours. I have not received a reply.\n\n"
                "If the content is still available, please remove it immediately, and confirm in "
                "writing what action you have taken. If it is not removed, I intend "
                "to appeal to the Grievance Appellate Committee and report the matter to the "
                "police.\n\nRegards,\n{{NAME}}\nDate: {{DATE}}")
        subject = "Follow-up: removal deadline passed (IT Rules 2021, Rule 3(2)(b))"
    return {"subject": subject, "body": body}


def drafts(state: State) -> State:
    todo = [r for r in state["reminders"] if r["kind"] in ("overdue", "no_reply_recorded", "refused")]
    llm = get_llm()
    out = []
    for r in todo[:MAX_DRAFTS]:
        platform = r["host"]
        draft, source, notes = _template(r["kind"], platform), "template", ["llm_not_configured"]
        if llm.available:
            sections, rules = allowed_citations(grounds_for(r["category"], r["self_taken"]))
            situation = ("The platform refused the removal request." if r["kind"] == "refused" else
                         f"No reply was recorded {r.get('hours_since_sent', 24)} hours after the "
                         "notice was sent; the legal deadline is 24 hours.")
            prompt = (f"Platform: {platform}\nSituation: {situation}\nGround to cite: Rule 3(2)(b) "
                      "of the IT Rules 2021. Mention that the sender may appeal to the Grievance "
                      "Appellate Committee and report to the police. Return JSON 'subject', 'body'.")
            data, _a, notes = llm_validated(
                llm, system=SYSTEM, prompt=prompt, schema=SCHEMA, max_tokens=2000,
                validate=lambda d: check_draft(d.get("body", ""), allowed_sections=sections,
                                               allowed_rules=rules, min_len=150, max_len=3000))
            if data is not None:
                draft, source = {"subject": data["subject"].strip(), "body": data["body"].strip()}, "llm"
        out.append({"id": r["link_id"], "link_id": r["link_id"], "case_id": r["case_id"],
                    "kind": r["kind"], "sent_at": r.get("sent_at"), "draft": draft,
                    "source": source, "notes": notes})
    return {"drafts": out, "steps": step(state, "drafts", note=str(len(out)))}


def approval(state: State) -> State:
    if not state["drafts"]:
        return {"approved_ids": [], "steps": step(state, "approval", note="nothing_to_approve")}
    decision = interrupt({"kind": "follow_up_drafts", "reminders": state["reminders"],
                          "drafts": state["drafts"]})
    ids = {d["id"] for d in state["drafts"]}
    chosen = []
    if isinstance(decision, dict) and decision.get("decision") == "approve":
        requested = decision.get("approved_ids")
        chosen = sorted(ids if requested is None else ids & set(requested))
    return {"approved_ids": chosen, "steps": step(state, "approval", note=str(len(chosen)))}


def apply(state: State) -> State:
    """Notes approved follow-ups on each link's timeline. Status is NOT
    changed: a draft is not a sent message, and sent is not resolved."""
    if not state["approved_ids"]:
        return {"applied": 0, "steps": step(state, "apply", note="0")}
    with SessionLocal() as db:
        n = 0
        for link_id in state["approved_ids"]:
            link = db.scalar(select(CaseLink).join(Case).where(
                CaseLink.id == link_id, Case.user_id == state["user_id"]))
            if link:
                link.events.append(StatusEvent(status=link.status,
                                               note="Follow-up message prepared (not yet sent)"))
                n += 1
        db.commit()
    return {"applied": n, "steps": step(state, "apply", note=str(n))}


def build_graph() -> StateGraph:
    g = StateGraph(State)
    g.add_node("scan", scan)
    g.add_node("drafts", drafts)
    g.add_node("approval", approval)
    g.add_node("apply", apply)
    g.add_edge(START, "scan")
    g.add_edge("scan", "drafts")
    g.add_edge("drafts", "approval")
    g.add_edge("approval", "apply")
    g.add_edge("apply", END)
    return g

"""Agent 3: Complaint Generation (section 17.10).

gather -> grounds -> draft -> approval (PAUSE for the user) -> finalize

- gather/grounds are deterministic: the case's category and the legal
  grounds come from our own rules, never from the model. gather also reads
  the latest check of the link (section 23.4): what was found becomes the
  notice's evidence (match strength only - never the image or the URL).
- draft asks the LLM (if configured) for a notice using placeholders
  {{URL}}, {{NAME}}, {{DATE}}. The model never sees the link, the user's
  name or any image. Its draft must pass guardrails (no invented laws, no
  links of its own, placeholders present) or we use the template.
- approval pauses the graph. Nothing is final until the user approves.
  Sending the notice is always the user's own action.
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from sqlalchemy import select

from app.agents.common import AgentInputError, llm_validated, step
from app.agents.legal import CATEGORY_LABEL, allowed_citations, grounds_for
from app.core.db import SessionLocal
from app.llm import get_llm
from app.llm.guardrails import check_draft
from app.models import Case, CaseLink, DiscoveredMatch, DiscoveryJob

NAME = "complaint"

SYSTEM = (
    "You draft formal takedown notices for people whose images were shared online without "
    "consent, to be sent to a platform's Grievance Officer or Trust and Safety team in India. "
    "Write clearly, firmly and politely, in plain English. Use ONLY the legal grounds you are "
    "given, quoting their rule and section numbers exactly; never add other laws. Never invent "
    "facts. Use the placeholders {{URL}} for the link, {{NAME}} for the sender's name and "
    "{{DATE}} for the date - never write a real link, name, email or date. Do not threaten, "
    "do not claim to be a lawyer and do not promise outcomes."
)

SCHEMA = {
    "type": "object",
    "properties": {"subject": {"type": "string"}, "body": {"type": "string"}},
    "required": ["subject", "body"],
    "additionalProperties": False,
}


class State(TypedDict, total=False):
    user_id: str
    case_id: str
    link_id: str
    platform_name: str
    category: str
    self_taken: bool | None
    grounds: list[dict]
    evidence: dict
    draft: dict
    source: str  # "llm" | "template"
    llm_attempts: int
    llm_notes: list[str]
    decision: str
    status: str
    steps: list[dict]


def gather(state: State) -> State:
    with SessionLocal() as db:
        case = db.scalar(select(Case).where(Case.id == state["case_id"],
                                            Case.user_id == state["user_id"]))
        link = case and db.scalar(select(CaseLink).where(CaseLink.id == state["link_id"],
                                                         CaseLink.case_id == case.id))
        if not case or not link:
            raise AgentInputError("case or link not found")
        return {"category": case.category, "self_taken": case.self_taken,
                "evidence": scan_evidence(db, link.id),
                "steps": step(state, "gather")}


RANK = {"exact": 0, "high": 1, "possible": 2}


def scan_evidence(db, link_id: str) -> dict:
    """Summary of the most recent finished check of this link."""
    job = db.scalar(select(DiscoveryJob).where(
        DiscoveryJob.case_link_id == link_id, DiscoveryJob.status.in_(("done", "failed")))
        .order_by(DiscoveryJob.created_at.desc()).limit(1))
    if job is None:
        return {"checked": False}
    if job.status == "failed":
        return {"checked": False, "blocked": job.error_code in ("forbidden", "robots")}
    matches = list(db.scalars(select(DiscoveredMatch).where(DiscoveredMatch.job_id == job.id)))
    best = min(matches, key=lambda m: (RANK[m.classification], m.phash_distance or 0), default=None)
    return {"checked": True, "images_checked": job.candidates_checked, "copies": len(matches),
            "best": best.classification if best else "none",
            "distance": best.phash_distance if best else None}


def evidence_sentence(ev: dict) -> str | None:
    """Plain-English evidence for the notice, or None if there is none."""
    if not ev.get("checked") or ev.get("copies", 0) == 0:
        return None
    n, k = ev["images_checked"], ev["copies"]
    how = {
        "exact": "an exact, file-for-file copy of my photograph",
        "high": f"a copy of my photograph that has been edited (for example cropped or filtered); "
                f"its image fingerprint differs from my original in only {ev['distance']} of 64 points",
        "possible": f"what appears to be an edited copy of my photograph; its image fingerprint "
                    f"differs from my original in {ev['distance']} of 64 points",
    }[ev["best"]]
    found = "one image" if k == 1 else f"{k} images"
    examined = "1 image" if n == 1 else f"{n} images"
    return (f"An automated image-fingerprint check of this page examined {examined} and found "
            f"{found} matching my photograph, including {how}.")


def select_grounds(state: State) -> State:
    return {"grounds": grounds_for(state["category"], state["self_taken"]),
            "steps": step(state, "grounds")}


def template_draft(category: str, platform: str, grounds: list[dict],
                   evidence: dict | None = None) -> dict:
    what = {
        "intimate": "an intimate image of me that was shared without my consent. I did not agree "
                    "to it being published anywhere.",
        "morphed": "a morphed or AI-generated image that uses my face or body to depict me in a "
                   "sexual or degrading way. It is fake and was made and shared without my consent.",
        "impersonation": "a fake profile that uses my photographs and pretends to be me. I did not "
                         "create it and have not authorised it.",
    }[category]
    lines = [
        f"To the Grievance Officer / Trust and Safety team, {platform},", "",
        "I am writing to request the immediate removal of content at the following link:",
        "{{URL}}", "", f"This link contains {what}", "",
        *([evidence_sentence(evidence), ""] if evidence and evidence_sentence(evidence) else []),
        "I ask you to remove this content and any copies of it on your service under:",
        *[f"{i}. {g['text']}" for i, g in enumerate(grounds, 1)], "",
        "Please remove the content within 24 hours as the IT Rules require, prevent it from being "
        "uploaded again, and confirm to me in writing once it has been removed. Please preserve the "
        "uploader's account details in case law enforcement requests them.", "",
        "I confirm that I am the person shown in this content (or am acting on their behalf with "
        "their permission), and that the information in this notice is accurate.", "",
        "Regards,", "{{NAME}}", "Date: {{DATE}}",
    ]
    subject = (f"Urgent removal request: {CATEGORY_LABEL[category].lower()} "
               "(IT Rules 2021, Rule 3(2)(b))")
    return {"subject": subject, "body": "\n".join(lines)}


def draft(state: State) -> State:
    platform = state.get("platform_name") or "your service"
    grounds = state["grounds"]
    ev = state.get("evidence") or {}
    found = evidence_sentence(ev)
    if found:
        evidence_note = ("Evidence (include it, in the sender's voice, as one short paragraph after "
                         f"describing the content): {found}")
    elif ev.get("blocked"):
        evidence_note = ("The page needs a login, so it could not be checked automatically. Do not "
                         "claim anything was verified; rely on the sender's own statement.")
    else:
        evidence_note = "No automated check result is available; do not mention one."
    llm = get_llm()
    if not llm.available:
        return {"draft": template_draft(state["category"], platform, grounds, ev), "source": "template",
                "llm_attempts": 0, "llm_notes": ["llm_not_configured"],
                "steps": step(state, "draft", note="template")}

    sections, rules = allowed_citations(grounds)
    prompt = (
        f"Platform: {platform}\n"
        f"What happened: {CATEGORY_LABEL[state['category']]}\n"
        f"Legal grounds (cite these and nothing else):\n"
        + "\n".join(f"- {g['text']}" for g in grounds)
        + f"\n{evidence_note}"
        + "\n\nAsk for removal within 24 hours, prevention of re-uploads, written confirmation, "
          "and preservation of the uploader's details for law enforcement. End with a "
          "confirmation that the sender is the person shown (or acting for them), then "
          "'Regards,', {{NAME}} and 'Date: {{DATE}}'. Write the body as short paragraphs "
          "separated by blank lines, with the link {{URL}} on a line of its own. "
          "Return JSON with 'subject' and 'body'."
    )

    def validate(d: dict) -> list[str]:
        problems = check_draft(d.get("body", ""), allowed_sections=sections, allowed_rules=rules)
        subject = d.get("subject", "")
        if not (10 <= len(subject) <= 200) or "{{" in subject:
            problems.append("subject must be 10-200 characters with no placeholders")
        return problems

    data, attempts, notes = llm_validated(llm, system=SYSTEM, prompt=prompt, schema=SCHEMA,
                                          validate=validate)
    if data is None:
        return {"draft": template_draft(state["category"], platform, grounds, ev), "source": "template",
                "llm_attempts": attempts, "llm_notes": [*notes, "fell_back_to_template"],
                "steps": step(state, "draft", ok=False, note="llm_failed_template_used")}
    return {"draft": {"subject": data["subject"].strip(), "body": data["body"].strip()},
            "source": "llm", "llm_attempts": attempts, "llm_notes": notes,
            "steps": step(state, "draft", note="llm")}


def approval(state: State) -> State:
    # Pauses here until the user decides. On resume this node re-runs and
    # interrupt() returns the decision instead of pausing.
    decision = interrupt({"kind": "complaint_draft", "draft": state["draft"],
                          "source": state["source"], "notes": state.get("llm_notes", [])})
    choice = decision.get("decision") if isinstance(decision, dict) else None
    return {"decision": "approve" if choice == "approve" else "reject",
            "steps": step(state, "approval", note=choice)}


def finalize(state: State) -> State:
    return {"status": "approved" if state["decision"] == "approve" else "rejected",
            "steps": step(state, "finalize")}


def build_graph() -> StateGraph:
    g = StateGraph(State)
    g.add_node("gather", gather)
    g.add_node("grounds", select_grounds)
    g.add_node("draft", draft)
    g.add_node("approval", approval)
    g.add_node("finalize", finalize)
    g.add_edge(START, "gather")
    g.add_edge("gather", "grounds")
    g.add_edge("grounds", "draft")
    g.add_edge("draft", "approval")
    g.add_edge("approval", "finalize")
    g.add_edge("finalize", END)
    return g

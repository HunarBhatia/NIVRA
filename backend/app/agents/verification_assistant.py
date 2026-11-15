"""Agent 2: Verification Assistant (section 17.9).

gather -> facts -> explain

Helps the user understand a match. It NEVER decides whether an image is
theirs or whether it was shared without consent - only the user does.
Facts and the evidence checklist are deterministic; the LLM (optional) only
rewords the facts into a short summary, and guardrails reject any wording
that claims certainty, consent status or legality.
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.agents.common import AgentInputError, llm_validated, step
from app.core.db import SessionLocal
from app.llm import get_llm
from app.llm.guardrails import check_explanation
from app.models import DiscoveredMatch, DiscoveryJob

NAME = "verification"

DISCLAIMER = ("Nivra compares fingerprints. It can't tell whether an image is yours or whether it "
              "was shared without consent - only you can decide that.")

SYSTEM = (
    "You explain image-matching results to someone who may be distressed. Use two or three short, "
    "calm, plain sentences. Describe only the facts given. Never say the image is theirs, never "
    "say it was shared without consent, never claim certainty and never make legal judgements. "
    "End by reminding them that they decide."
)
SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
    "additionalProperties": False,
}


class State(TypedDict, total=False):
    user_id: str
    match_id: str
    classification: str
    phash_distance: int | None
    sha256_equal: bool
    match_status: str
    in_case: bool
    page_has_title: bool
    facts: list[str]
    missing_evidence: list[str]
    next_step: str
    summary: str
    source: str
    llm_notes: list[str]
    steps: list[dict]


def gather(state: State) -> State:
    with SessionLocal() as db:
        m = db.scalar(select(DiscoveredMatch).where(DiscoveredMatch.id == state["match_id"],
                                                    DiscoveredMatch.user_id == state["user_id"]))
        if not m:
            raise AgentInputError("match not found")
        job = db.get(DiscoveryJob, m.job_id) if m.job_id else None
        return {"classification": m.classification, "phash_distance": m.phash_distance,
                "sha256_equal": m.sha256_equal, "match_status": m.status,
                "in_case": m.case_link_id is not None,
                "page_has_title": bool(job and job.page_title), "steps": step(state, "gather")}


def facts(state: State) -> State:
    d = state.get("phash_distance")
    cls = state["classification"]
    if cls == "exact":
        why = ["The found file is byte-for-byte identical to the image you protected."]
    elif cls == "high":
        why = [f"The found image looks almost the same: {d} of 64 visual-fingerprint bits differ "
               "(6 or fewer counts as very likely the same image).",
               "This usually means the same photo, resized or recompressed."]
    else:
        why = [f"There is some similarity: {d} of 64 visual-fingerprint bits differ (up to 12 counts "
               "as possible).",
               "Different photos that look alike can land here, so please check carefully."]
    evidence = ["A screenshot of the page showing the image, the web address and the date "
                "(before it is removed)."]
    if cls == "possible":
        evidence.append("A look at the page yourself, or by someone you trust, to check it really "
                        "is your image.")
    evidence.append("The username or account that posted it, if it's visible.")
    if not state["in_case"]:
        evidence.append("Add the page to a case so a takedown notice can be prepared.")
    status = state["match_status"]
    next_step = ("Decide whether this is your image." if status == "pending" else
                 "Send the notice from your case." if state["in_case"] else
                 "Add this page to a case." if status == "confirmed" else
                 "Nothing to do: you dismissed this match.")
    return {"facts": why, "missing_evidence": evidence, "next_step": next_step,
            "steps": step(state, "facts")}


def explain(state: State) -> State:
    fallback = " ".join(state["facts"]) + " You decide whether it's your image."
    llm = get_llm()
    if not llm.available:
        return {"summary": fallback, "source": "template", "llm_notes": ["llm_not_configured"],
                "steps": step(state, "explain", note="template")}
    prompt = ("Facts about one possible match (no image is available to you):\n- "
              + "\n- ".join(state["facts"]) + "\nReturn JSON with 'summary'.")
    data, _attempts, notes = llm_validated(
        llm, system=SYSTEM, prompt=prompt, schema=SCHEMA, max_tokens=1500,
        validate=lambda d: check_explanation(d.get("summary", "")))
    if data is None:
        return {"summary": fallback, "source": "template", "llm_notes": [*notes, "fell_back"],
                "steps": step(state, "explain", ok=False, note="llm_failed_template_used")}
    return {"summary": data["summary"].strip(), "source": "llm", "llm_notes": notes,
            "steps": step(state, "explain", note="llm")}


def build_graph() -> StateGraph:
    g = StateGraph(State)
    g.add_node("gather", gather)
    g.add_node("facts", facts)
    g.add_node("explain", explain)
    g.add_edge(START, "gather")
    g.add_edge("gather", "facts")
    g.add_edge("facts", "explain")
    g.add_edge("explain", END)
    return g

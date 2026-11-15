"""Nivra's four AI agents (phase 5, PROJECT_DETAILS.txt section 17).

Each agent is a LangGraph graph of small nodes. Deterministic nodes do the
facts, rules and database work; the optional LLM node only drafts or
rewords text, and its output is validated before use. Consequential steps
pause on interrupt() until the user approves.

- discovery_coordinator  plans which pages to (re)check -> user approves
- verification_assistant explains a match; never decides it
- complaint_generator    drafts a takedown notice -> user approves
- follow_up              finds deadlines, drafts follow-ups -> user approves
"""

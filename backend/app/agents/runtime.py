"""Where agents run (D16): in this backend (default) or on Maritime (optional).

LocalRuntime compiles the LangGraph graphs with a SQLite checkpointer, so a
run paused for approval survives restarts and is resumed by thread_id. In
production use LangGraph's Postgres checkpointer instead.

MaritimeRuntime is an OPTIONAL adapter for running the same agents on
Maritime (maritime.sh). It uses only the documented chat endpoint
POST /api/agents/{id}/chat {"message"} -> {"response"}, and requires our agent
container (app/agents/serve.py) deployed there. Untested against the live
service (no account/key); off by default.
"""

import json
import sqlite3
import threading
from typing import Any, Protocol

import httpx
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from app.agents import complaint_generator, discovery_coordinator, follow_up, verification_assistant
from app.core.config import get_settings

AGENTS = {
    m.NAME: m for m in (complaint_generator, verification_assistant, follow_up, discovery_coordinator)
}


class RunResult(dict):
    """{"state": final or paused state, "interrupt": payload or None}"""


class AgentRuntime(Protocol):
    def start(self, agent: str, run_id: str, state: dict[str, Any]) -> RunResult: ...
    def resume(self, agent: str, run_id: str, decision: dict[str, Any]) -> RunResult: ...


def _result(out: dict[str, Any]) -> RunResult:
    interrupts = out.get("__interrupt__") or []
    payload = interrupts[0].value if interrupts else None
    state = {k: v for k, v in out.items() if k != "__interrupt__"}
    return RunResult(state=state, interrupt=payload)


class LocalRuntime:
    def __init__(self, checkpoint_path: str):
        conn = sqlite3.connect(checkpoint_path, check_same_thread=False)
        self.saver = SqliteSaver(conn)
        self._lock = threading.Lock()
        self.graphs = {name: m.build_graph().compile(checkpointer=self.saver)
                       for name, m in AGENTS.items()}

    def _cfg(self, run_id: str) -> dict:
        return {"configurable": {"thread_id": run_id}}

    def start(self, agent: str, run_id: str, state: dict[str, Any]) -> RunResult:
        with self._lock:
            return _result(self.graphs[agent].invoke(state, self._cfg(run_id)))

    def resume(self, agent: str, run_id: str, decision: dict[str, Any]) -> RunResult:
        with self._lock:
            return _result(self.graphs[agent].invoke(Command(resume=decision), self._cfg(run_id)))

    def is_paused(self, agent: str, run_id: str) -> bool:
        snap = self.graphs[agent].get_state(self._cfg(run_id))
        return bool(snap and snap.next)


class MaritimeRuntime:
    """Sends {"op", "agent", "run_id", "payload"} as a chat message to our agent
    container on Maritime, which runs LocalRuntime and replies with the
    JSON-encoded RunResult."""

    def __init__(self, *, api_key: str, agent_id: str, base_url: str):
        self.agent_id = agent_id
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def _send(self, body: dict[str, Any]) -> RunResult:
        r = httpx.post(f"{self.base_url}/api/agents/{self.agent_id}/chat", headers=self.headers,
                       json={"message": json.dumps(body)}, timeout=60)
        r.raise_for_status()
        return RunResult(json.loads(r.json()["response"]))

    def start(self, agent: str, run_id: str, state: dict[str, Any]) -> RunResult:
        return self._send({"op": "start", "agent": agent, "run_id": run_id, "payload": state})

    def resume(self, agent: str, run_id: str, decision: dict[str, Any]) -> RunResult:
        return self._send({"op": "resume", "agent": agent, "run_id": run_id, "payload": decision})


_runtime: AgentRuntime | None = None


def get_runtime() -> AgentRuntime:
    global _runtime
    if _runtime is None:
        s = get_settings()
        if s.agent_runtime == "maritime" and s.maritime_api_key and s.maritime_agent_id:
            _runtime = MaritimeRuntime(api_key=s.maritime_api_key, agent_id=s.maritime_agent_id,
                                       base_url=s.maritime_base_url)
        else:
            _runtime = LocalRuntime(s.agent_checkpoint_path)
    return _runtime


def reset_runtime(runtime: AgentRuntime | None = None) -> None:
    """Tests: swap in a fresh runtime (e.g. to simulate a restart)."""
    global _runtime
    _runtime = runtime

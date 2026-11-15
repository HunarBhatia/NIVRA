"""Minimal agent server matching Maritime's custom-container contract
(bind $PORT, GET /health, POST /chat replying {"response": "..."}).

Only needed if NIVRA_AGENT_RUNTIME=maritime. The container would also need
database access, which is a deployment decision still to be made (17.13).
Run locally:  python -m uvicorn app.agents.serve:app --port 8080
"""

import json

from fastapi import FastAPI
from pydantic import BaseModel

from app.agents.runtime import LocalRuntime
from app.core.config import get_settings

app = FastAPI(title="Nivra agents")
_runtime = LocalRuntime(get_settings().agent_checkpoint_path)


class ChatIn(BaseModel):
    message: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
def chat(body: ChatIn) -> dict[str, str]:
    req = json.loads(body.message)
    if req["op"] == "start":
        result = _runtime.start(req["agent"], req["run_id"], req["payload"])
    else:
        result = _runtime.resume(req["agent"], req["run_id"], req["payload"])
    return {"response": json.dumps(result, default=str)}

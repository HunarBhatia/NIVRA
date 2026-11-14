"""The four agents: happy paths, guardrails, retries, fallbacks, approvals,
failures, restart recovery, privacy of LLM prompts, and the Gemini provider
request shape (mocked HTTP - no real API calls)."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agents.runtime import LocalRuntime, reset_runtime
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.llm import LLMError
from app.llm.gemini_provider import GeminiProvider
from app.llm.factory import set_llm_for_tests
from app.llm.guardrails import check_draft, check_explanation
from app.models import CaseLink, DiscoveredMatch, DiscoveryJob, StatusEvent
from tests.conftest import register
from tests.test_discovery import protect

URL = "https://site.test/leak/123"
GOOD_BODY = ("To the Grievance Officer, Instagram,\n\nI request removal of the content at {{URL}}. "
             "It is an intimate image of me shared without my consent. Under Rule 3(2)(b) of the "
             "IT Rules 2021 and Section 66E, Section 67 and Section 67A of the IT Act you must act "
             "within 24 hours. Please remove it, prevent re-uploads, confirm in writing and preserve "
             "the uploader's details for law enforcement. I confirm I am the person shown.\n\n"
             "Regards,\n{{NAME}}\nDate: {{DATE}}")


class FakeLLM:
    """Scripted stand-in for Claude. Records every prompt it receives."""

    name, model = "fake", "fake-model"

    def __init__(self, *script):
        self.script = list(script)
        self.prompts: list[str] = []

    @property
    def available(self) -> bool:
        return True

    def generate_json(self, *, system, prompt, schema, max_tokens=4000):
        self.prompts.append(system + "\n" + prompt)
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def fresh_runtime():
    reset_runtime(None)
    set_llm_for_tests(None)
    yield
    set_llm_for_tests(None)
    reset_runtime(None)


def case_with_link(c: TestClient, name="Priya Test", urls=(URL,)) -> tuple[str, list[str]]:
    case = c.post("/api/cases", json={"category": "intimate", "self_taken": False,
                                      "display_name": name, "urls": list(urls)}).json()
    return case["id"], [link["id"] for link in case["links"]]


def draft(c: TestClient, case_id: str, link_id: str):
    return c.post("/api/agents/complaint",
                  json={"case_id": case_id, "link_id": link_id, "platform_name": "Instagram"})


# ---------------- Complaint agent ----------------

def test_complaint_without_llm_uses_template_and_waits_for_approval(user_client: TestClient):
    case_id, (link_id,) = case_with_link(user_client)
    r = draft(user_client, case_id, link_id)
    assert r.status_code == 201
    run = r.json()
    assert run["status"] == "awaiting_approval" and run["used_llm"] is False
    assert run["output"]["source"] == "template"
    assert "{{URL}}" in run["output"]["draft"]["body"]  # stored with placeholders
    assert URL in run["preview"]["body"] and "Priya Test" in run["preview"]["body"]
    assert "Instagram" in run["preview"]["body"]

    done = user_client.post(f"/api/agents/runs/{run['id']}/decision", json={"decision": "approve"})
    assert done.json()["status"] == "completed" and done.json()["output"]["approved"] is True
    again = user_client.post(f"/api/agents/runs/{run['id']}/decision", json={"decision": "approve"})
    assert again.status_code == 409


def test_complaint_llm_draft_used_and_prompt_has_no_personal_data(user_client: TestClient):
    fake = FakeLLM({"subject": "Urgent removal request under IT Rules", "body": GOOD_BODY})
    set_llm_for_tests(fake)
    case_id, (link_id,) = case_with_link(user_client)
    run = draft(user_client, case_id, link_id).json()
    assert run["used_llm"] is True and run["output"]["source"] == "llm"
    assert URL in run["preview"]["body"] and "Priya Test" in run["preview"]["body"]
    sent = "\n".join(fake.prompts)
    assert URL not in sent and "site.test" not in sent and "Priya" not in sent


def test_invented_law_is_rejected_then_fixed(user_client: TestClient):
    bad = {"subject": "Urgent removal request", "body": GOOD_BODY + "\nAlso Section 420 IPC."}
    fake = FakeLLM(bad, {"subject": "Urgent removal request under IT Rules", "body": GOOD_BODY})
    set_llm_for_tests(fake)
    case_id, (link_id,) = case_with_link(user_client)
    run = draft(user_client, case_id, link_id).json()
    assert run["output"]["source"] == "llm" and len(fake.prompts) == 2
    assert "Section 420" in fake.prompts[1]  # the problem was fed back to the model


def test_always_invalid_llm_falls_back_to_template(user_client: TestClient):
    fake = FakeLLM({"subject": "Removal request please", "body": GOOD_BODY.replace("{{URL}}", "the link")})
    set_llm_for_tests(fake)
    case_id, (link_id,) = case_with_link(user_client)
    run = draft(user_client, case_id, link_id).json()
    assert len(fake.prompts) == 3
    assert run["output"]["source"] == "template" and run["used_llm"] is False
    assert "fell_back_to_template" in run["output"]["notes"]


@pytest.mark.parametrize("error,calls", [(LLMError("auth"), 1), (LLMError("refusal"), 1),
                                         (LLMError("rate_limited", retryable=True), 3)])
def test_llm_errors_fall_back(user_client: TestClient, error, calls):
    fake = FakeLLM(error)
    set_llm_for_tests(fake)
    case_id, (link_id,) = case_with_link(user_client)
    run = draft(user_client, case_id, link_id).json()
    assert run["status"] == "awaiting_approval" and run["output"]["source"] == "template"
    assert len(fake.prompts) == calls


def test_retryable_error_then_success(user_client: TestClient):
    fake = FakeLLM(LLMError("rate_limited", retryable=True),
                   {"subject": "Urgent removal request under IT Rules", "body": GOOD_BODY})
    set_llm_for_tests(fake)
    case_id, (link_id,) = case_with_link(user_client)
    assert draft(user_client, case_id, link_id).json()["output"]["source"] == "llm"


def test_reject_decision(user_client: TestClient):
    case_id, (link_id,) = case_with_link(user_client)
    run = draft(user_client, case_id, link_id).json()
    out = user_client.post(f"/api/agents/runs/{run['id']}/decision", json={"decision": "reject"}).json()
    assert out["status"] == "rejected" and out["output"]["approved"] is False


def test_unexpected_crash_is_recorded_as_failed(user_client: TestClient):
    set_llm_for_tests(FakeLLM(ValueError("boom")))
    case_id, (link_id,) = case_with_link(user_client)
    run = draft(user_client, case_id, link_id).json()
    assert run["status"] == "failed" and run["error_code"] == "ValueError"


def test_paused_run_survives_restart(user_client: TestClient):
    case_id, (link_id,) = case_with_link(user_client)
    run = draft(user_client, case_id, link_id).json()
    # Simulate the server restarting: a brand-new runtime on the same checkpoint file.
    reset_runtime(LocalRuntime(get_settings().agent_checkpoint_path))
    out = user_client.post(f"/api/agents/runs/{run['id']}/decision", json={"decision": "approve"})
    assert out.json()["status"] == "completed"


def test_agents_are_private_to_their_account(client: TestClient):
    register(client)
    case_id, (link_id,) = case_with_link(client)
    run = draft(client, case_id, link_id).json()
    client.post("/api/auth/logout")
    register(client)
    assert draft(client, case_id, link_id).status_code == 404
    assert client.get(f"/api/agents/runs/{run['id']}").status_code == 404
    assert client.post(f"/api/agents/runs/{run['id']}/decision",
                       json={"decision": "approve"}).status_code == 404
    assert client.get("/api/agents/runs").json() == []


# ---------------- Verification assistant ----------------

def _match(client: TestClient) -> str:
    protect(client)
    from tests.test_discovery import run as run_job
    jid = client.post("/api/discovery/jobs", json={"url": "https://site.test/thread"}).json()["id"]
    run_job(jid)
    return client.get("/api/matches").json()[0]["id"]


def test_verification_without_llm(user_client: TestClient):
    mid = _match(user_client)
    run = user_client.post("/api/agents/verification", json={"match_id": mid}).json()
    out = run["output"]
    assert run["status"] == "completed" and out["source"] == "template"
    assert out["classification"] in ("exact", "high")
    assert out["missing_evidence"] and "only you can decide" in out["disclaimer"]
    assert out["next_step"] == "Decide whether this is your image."


def test_verification_guardrail_blocks_overclaiming(user_client: TestClient):
    mid = _match(user_client)
    set_llm_for_tests(FakeLLM({"summary": "This is definitely your image and it is illegal."}))
    out = user_client.post("/api/agents/verification", json={"match_id": mid}).json()["output"]
    assert out["source"] == "template"
    assert "definitely" not in out["summary"]


def test_verification_llm_summary_used_when_safe(user_client: TestClient):
    mid = _match(user_client)
    set_llm_for_tests(FakeLLM({"summary": "The image found looks almost the same as one you "
                                          "protected. You decide whether it's yours."}))
    out = user_client.post("/api/agents/verification", json={"match_id": mid}).json()["output"]
    assert out["source"] == "llm"


# ---------------- Follow-up agent ----------------

def _age_link(link_id: str, status: str, hours_ago: float | None) -> None:
    with SessionLocal() as db:
        link = db.get(CaseLink, link_id)
        link.status = status
        link.reported_at = datetime.now(UTC) - timedelta(hours=hours_ago) if hours_ago else None
        db.commit()


def test_follow_up_finds_deadlines_and_needs_approval(user_client: TestClient):
    case_id, ids = case_with_link(user_client, urls=("site.test/a", "site.test/b", "site.test/c",
                                                     "site.test/d"))
    _age_link(ids[0], "reported", 30)   # overdue
    _age_link(ids[1], "reported", 20)   # due soon
    _age_link(ids[2], "rejected", 50)   # refused
    _age_link(ids[3], "removed", 40)    # nothing to do
    run = user_client.post("/api/agents/follow-up").json()
    assert run["status"] == "awaiting_approval"
    kinds = {r["link_id"]: r["kind"] for r in run["output"]["reminders"]}
    assert kinds == {ids[0]: "overdue", ids[1]: "due_soon", ids[2]: "refused"}
    previews = {p["link_id"]: p for p in run["previews"]}
    assert set(previews) == {ids[0], ids[2]}
    assert "https://site.test/a" in previews[ids[0]]["body"] and "{{" not in previews[ids[0]]["body"]

    out = user_client.post(f"/api/agents/runs/{run['id']}/decision",
                           json={"decision": "approve", "approved_ids": [ids[0]]}).json()
    assert out["status"] == "completed" and out["output"]["applied"] == 1
    with SessionLocal() as db:
        link = db.get(CaseLink, ids[0])
        notes = [e.note for e in db.scalars(select(StatusEvent).where(StatusEvent.link_id == ids[0]))]
    assert link.status == "reported"  # a prepared message is not a sent or resolved one
    assert "Follow-up message prepared (not yet sent)" in notes


def test_follow_up_with_nothing_due_completes_immediately(user_client: TestClient):
    case_with_link(user_client)
    run = user_client.post("/api/agents/follow-up").json()
    assert run["status"] == "completed" and run["output"]["reminders"] == []


# ---------------- Discovery coordinator ----------------

def test_coordinator_needs_an_active_image(user_client: TestClient):
    run = user_client.post("/api/agents/discovery", json={"urls": ["https://site.test/x"]}).json()
    assert run["status"] == "completed" and "Protect at least one image" in run["output"]["message"]


def test_coordinator_plans_dedupes_and_waits_for_approval(user_client: TestClient):
    protect(user_client)
    _case, (link_id,) = case_with_link(user_client, urls=("https://site.test/removed",))
    _age_link(link_id, "removed", 5)
    user_client.post("/api/discovery/jobs", json={"url": "https://site.test/recent"})
    run = user_client.post("/api/agents/discovery", json={"urls": [
        "site.test/new", "https://site.test/recent", "site.test/new", "javascript:x"]}).json()
    assert run["status"] == "awaiting_approval"
    plan = {p["url"]: p for p in run["output"]["plan"]}
    assert set(plan) == {"https://site.test/new", "https://site.test/removed"}
    whys = {s["url"]: s["why"] for s in run["output"]["skipped"]}
    assert "24 hours" in whys["https://site.test/recent"] and "web link" in whys["javascript:x"]

    approve = [plan["https://site.test/new"]["id"]]
    out = user_client.post(f"/api/agents/runs/{run['id']}/decision",
                           json={"decision": "approve", "approved_ids": approve}).json()
    assert out["status"] == "completed" and len(out["output"]["job_ids"]) == 1
    with SessionLocal() as db:
        urls = set(db.scalars(select(DiscoveryJob.input_url)))
    assert "https://site.test/new" in urls and "https://site.test/removed" not in urls


def test_coordinator_rejection_queues_nothing(user_client: TestClient):
    protect(user_client)
    run = user_client.post("/api/agents/discovery", json={"urls": ["site.test/zzz"]}).json()
    before = _job_count()
    user_client.post(f"/api/agents/runs/{run['id']}/decision", json={"decision": "reject"})
    assert _job_count() == before


def _job_count() -> int:
    with SessionLocal() as db:
        return len(db.scalars(select(DiscoveryJob)).all())


# ---------------- Guardrails ----------------

def test_check_draft_rules():
    allowed = dict(allowed_sections={"66E", "67", "67A"}, allowed_rules={"3(2)(b)", "3(1)(b)"})
    assert check_draft(GOOD_BODY, **allowed) == []
    probs = check_draft(GOOD_BODY + " See https://evil.example and Section 509 and Rule 4(1).",
                        **allowed)
    joined = " ".join(probs)
    assert "link" in joined and "509" in joined and "4(1)" in joined
    assert any("{{URL}}" in p for p in check_draft(GOOD_BODY.replace("{{URL}}", "x"), **allowed))
    assert any("lawyer" in p for p in check_draft(GOOD_BODY + " I am a lawyer.", **allowed))


def test_check_explanation_rules():
    assert check_explanation("This looks similar to one you protected. You decide.") == []
    assert check_explanation("This proves it is non-consensual.") != []


# ---------------- Gemini provider (mocked HTTP) ----------------

def _provider(handler) -> GeminiProvider:
    return GeminiProvider(api_key="test-key", model="gemini-3.1-flash-lite",
                          http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def _reply(text: str, finish="STOP") -> dict:
    return {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]},
                            "finishReason": finish}],
            "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 5}}


def test_gemini_request_shape_and_parsing():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_reply('{"summary": "ok"}'))

    schema = {"type": "object", "properties": {"summary": {"type": "string"}},
              "required": ["summary"]}
    out = _provider(handler).generate_json(system="be calm", prompt="facts", schema=schema,
                                           max_tokens=1500)
    body = seen["body"]
    assert out == {"summary": "ok"}
    assert "models/gemini-3.1-flash-lite:generateContent" in seen["url"]
    assert body["systemInstruction"]["parts"][0]["text"] == "be calm"
    assert body["contents"][0]["parts"][0]["text"] == "facts"
    cfg = body["generationConfig"]
    assert cfg["responseMimeType"] == "application/json"
    assert cfg["responseJsonSchema"] == schema and cfg["maxOutputTokens"] == 1500


def test_gemini_error_and_block_mapping():
    def call(handler):
        return _provider(handler).generate_json(system="s", prompt="p", schema={"type": "object"})

    with pytest.raises(LLMError) as e:
        call(lambda r: httpx.Response(200, json=_reply("", "SAFETY")))
    assert e.value.code == "refusal" and not e.value.retryable
    with pytest.raises(LLMError) as e:
        call(lambda r: httpx.Response(200, json=_reply('{"a":', "MAX_TOKENS")))
    assert e.value.code == "truncated" and e.value.retryable
    with pytest.raises(LLMError) as e:
        call(lambda r: httpx.Response(429, json={"error": {"code": 429, "message": "slow",
                                                           "status": "RESOURCE_EXHAUSTED"}}))
    assert e.value.code == "rate_limited" and e.value.retryable
    with pytest.raises(LLMError) as e:
        call(lambda r: httpx.Response(404, json={"error": {"code": 404, "message": "no model",
                                                           "status": "NOT_FOUND"}}))
    assert e.value.code == "model_not_found" and not e.value.retryable


def test_gemini_is_the_default_provider_when_a_key_is_set(monkeypatch):
    from app.core import config
    from app.llm import factory
    monkeypatch.setenv("NIVRA_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    config.get_settings.cache_clear()
    factory._configured.cache_clear()
    try:
        llm = factory.get_llm()
        assert llm.name == "gemini" and llm.model == "gemini-3.1-flash-lite" and llm.available
    finally:
        monkeypatch.delenv("GEMINI_API_KEY")
        monkeypatch.setenv("NIVRA_LLM_PROVIDER", "none")
        config.get_settings.cache_clear()
        factory._configured.cache_clear()


def test_status_endpoint_reports_no_llm_by_default(client: TestClient):
    assert client.get("/api/agents/status").json()["llm_available"] is False
    assert DiscoveredMatch  # imported for fixtures

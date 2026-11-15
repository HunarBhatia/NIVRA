"""Phase 6: shared platform directory, complaint lifecycle, timeline,
overview, and the encrypted evidence locker."""

import base64
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import CaseLink, EvidenceItem
from app.platforms import all_platforms, resolve
from tests.conftest import PASS, register
from tests.test_agents import case_with_link, draft

ROOT = Path(__file__).resolve().parents[2]
URL = "https://instagram.com/p/leak1"


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


# ---------------- Platform directory ----------------

def test_website_and_backend_share_one_platform_file():
    shared = (ROOT / "shared" / "platforms.json").read_text(encoding="utf-8")
    web = (ROOT / "web" / "src" / "data" / "platforms.json").read_text(encoding="utf-8")
    assert json.loads(shared) == json.loads(web), "run: node web/scripts/sync-platforms.mjs"


def test_every_platform_has_the_required_fields_and_is_marked_unverified():
    keys = {"id", "name", "domains", "expected_hours", "mechanisms", "required_info",
            "required_evidence", "submission_steps", "status_tracking", "verified", "last_verified"}
    for p in all_platforms():
        assert keys <= set(p), p["id"]
        assert p["verified"] is False and p["last_verified"] is None
        assert p["status_tracking"] in ("email", "in_app", "ticket", "none")
        assert p["mechanisms"] and p["required_info"]
    assert resolve("m.facebook.com")["id"] == "facebook"
    assert resolve("unknown.example") is None


def test_platform_api(client: TestClient):
    data = client.get("/api/platforms").json()
    assert len(data["platforms"]) == 12 and "PROTOTYPE" in data["note"]
    assert client.get("/api/platforms/telegram").json()["status_tracking"] == "none"
    assert client.get("/api/platforms/nope").status_code == 404


# ---------------- Complaints ----------------

def template_complaint(c: TestClient, link_id: str) -> dict:
    r = c.post(f"/api/links/{link_id}/complaints", json={
        "subject": "Removal request", "source": "template",
        "body": "Please remove the content at {{URL}} under Rule 3(2)(b). Regards, {{NAME}} {{DATE}}"})
    assert r.status_code == 201, r.text
    return r.json()


def move(c: TestClient, cid: str, status: str, **extra):
    return c.post(f"/api/complaints/{cid}/status", json={"status": status, **extra})


def link_status(link_id: str) -> str:
    with SessionLocal() as db:
        return db.get(CaseLink, link_id).status


def test_complaint_lifecycle_updates_the_link(user_client: TestClient):
    case_id, (link_id,) = case_with_link(user_client, urls=(URL,))
    comp = template_complaint(user_client, link_id)
    assert comp["status"] == "user_approved" and comp["platform_name"] == "Instagram"
    assert URL in comp["body"] and "Priya Test" in comp["body"]  # placeholders filled
    assert comp["next_statuses"] == ["submitted_by_user", "sent_by_nivra", "discarded"]

    r = move(user_client, comp["id"], "submitted_by_user", channel_kind="in-app",
             channel_label="Report inside the Instagram app")
    assert r.json()["submitted_at"] and link_status(link_id) == "reported"
    r = move(user_client, comp["id"], "submission_confirmed", reference="IG-12345")
    assert r.json()["reference"] == "IG-12345"
    r = move(user_client, comp["id"], "resolved", note="They removed it")
    assert r.json()["status"] == "resolved" and link_status(link_id) == "removed"
    assert [e["status"] for e in r.json()["events"]] == [
        "user_approved", "submitted_by_user", "submission_confirmed", "resolved"]
    assert move(user_client, comp["id"], "rejected").status_code == 409  # final


def test_cannot_skip_steps_or_discard_after_sending(user_client: TestClient):
    _case, (link_id,) = case_with_link(user_client)
    comp = template_complaint(user_client, link_id)
    assert move(user_client, comp["id"], "resolved").status_code == 409
    move(user_client, comp["id"], "submitted_by_user")
    assert user_client.delete(f"/api/complaints/{comp['id']}").status_code == 409


def test_rejection_marks_the_link_refused(user_client: TestClient):
    _case, (link_id,) = case_with_link(user_client)
    comp = template_complaint(user_client, link_id)
    move(user_client, comp["id"], "submitted_by_user")
    move(user_client, comp["id"], "response_received", note="They asked for ID")
    move(user_client, comp["id"], "rejected")
    assert link_status(link_id) == "rejected"


def test_discarded_drafts_are_hidden(user_client: TestClient):
    case_id, (link_id,) = case_with_link(user_client)
    comp = template_complaint(user_client, link_id)
    assert user_client.delete(f"/api/complaints/{comp['id']}").status_code == 204
    assert user_client.get(f"/api/cases/{case_id}/complaints").json() == []


def test_assistant_drafts_become_tracked_complaints(user_client: TestClient):
    case_id, (link_id,) = case_with_link(user_client)
    run = draft(user_client, case_id, link_id).json()
    comps = user_client.get(f"/api/cases/{case_id}/complaints").json()
    assert [c["status"] for c in comps] == ["draft_generated"]
    assert run["output"]["complaint_id"] == comps[0]["id"]
    user_client.post(f"/api/agents/runs/{run['id']}/decision", json={"decision": "approve"})
    assert user_client.get(f"/api/cases/{case_id}/complaints").json()[0]["status"] == "user_approved"

    run2 = draft(user_client, case_id, link_id).json()
    user_client.post(f"/api/agents/runs/{run2['id']}/decision", json={"decision": "reject"})
    statuses = [c["status"] for c in user_client.get(f"/api/cases/{case_id}/complaints").json()]
    assert statuses == ["user_approved"]  # the rejected draft was discarded


def test_complaints_are_private(client: TestClient):
    register(client)
    case_id, (link_id,) = case_with_link(client)
    comp = template_complaint(client, link_id)
    client.post("/api/auth/logout")
    register(client)
    assert client.get(f"/api/cases/{case_id}/complaints").status_code == 404
    assert move(client, comp["id"], "submitted_by_user").status_code == 404
    assert client.post(f"/api/links/{link_id}/complaints", json={
        "subject": "x" * 10, "body": "y" * 60}).status_code == 404


# ---------------- Evidence locker ----------------

LOCKER = {"salt": b64(os.urandom(16)), "key_check": b64(os.urandom(44))}


def setup_locker(c: TestClient) -> None:
    assert c.post("/api/evidence/locker", json=LOCKER).status_code == 201


def add(c: TestClient, case_id: str, kind="note", blob: bytes | None = None, **extra):
    body = {"kind": kind, "enc_meta": b64(os.urandom(64)), **extra}
    if blob is not None:
        body["blob"] = b64(blob)
    return c.post(f"/api/cases/{case_id}/evidence", json=body)


def test_locker_setup_once(user_client: TestClient):
    assert user_client.get("/api/evidence/locker").json() == {"initialized": False}
    setup_locker(user_client)
    got = user_client.get("/api/evidence/locker").json()
    assert got["salt"] == LOCKER["salt"] and got["key_check"] == LOCKER["key_check"]
    assert user_client.post("/api/evidence/locker", json=LOCKER).status_code == 409


def test_evidence_needs_a_locker_and_matching_payload(user_client: TestClient):
    case_id, _ = case_with_link(user_client)
    assert add(user_client, case_id).status_code == 409
    setup_locker(user_client)
    assert add(user_client, case_id, "screenshot").status_code == 422  # missing file
    assert add(user_client, case_id, "note", blob=b"x").status_code == 422  # note with file
    assert add(user_client, case_id, "note").status_code == 201


def test_server_stores_exactly_the_ciphertext_it_was_given(user_client: TestClient):
    case_id, (link_id,) = case_with_link(user_client)
    setup_locker(user_client)
    cipher = os.urandom(5000)
    item = add(user_client, case_id, "screenshot", blob=cipher, link_id=link_id).json()
    assert item["size"] == 5000 and item["has_blob"]
    path = Path(get_settings().evidence_dir) / f"{item['id']}.bin"
    assert path.read_bytes() == cipher
    back = user_client.get(f"/api/evidence/{item['id']}/blob").json()["blob"]
    assert base64.b64decode(back) == cipher
    listed = user_client.get(f"/api/cases/{case_id}/evidence").json()
    assert listed[0]["enc_meta"] == item["enc_meta"] and listed[0]["link_id"] == link_id


def test_evidence_size_limit(user_client: TestClient):
    case_id, _ = case_with_link(user_client)
    setup_locker(user_client)
    big = os.urandom(get_settings().evidence_max_item_bytes + 1)
    assert add(user_client, case_id, "file", blob=big).status_code == 413


def test_deleting_evidence_case_or_account_removes_files(user_client: TestClient):
    case_id, _ = case_with_link(user_client)
    setup_locker(user_client)
    store = Path(get_settings().evidence_dir)
    one = add(user_client, case_id, "file", blob=b"a" * 100).json()["id"]
    assert user_client.delete(f"/api/evidence/{one}").status_code == 204
    assert not (store / f"{one}.bin").exists()

    two = add(user_client, case_id, "file", blob=b"b" * 100).json()["id"]
    user_client.delete(f"/api/cases/{case_id}")
    assert not (store / f"{two}.bin").exists()

    case2, _ = case_with_link(user_client)
    three = add(user_client, case2, "file", blob=b"c" * 100).json()["id"]
    user_client.request("DELETE", "/api/account", json={"passphrase": PASS})
    assert not (store / f"{three}.bin").exists()
    with SessionLocal() as db:
        assert db.scalar(select(EvidenceItem)) is None


def test_evidence_is_private(client: TestClient):
    register(client)
    case_id, _ = case_with_link(client)
    setup_locker(client)
    item = add(client, case_id, "file", blob=b"secret").json()
    client.post("/api/auth/logout")
    register(client)
    assert client.get(f"/api/evidence/{item['id']}/blob").status_code == 404
    assert client.get(f"/api/cases/{case_id}/evidence").status_code == 404
    assert client.delete(f"/api/evidence/{item['id']}").status_code == 404


def test_evidence_link_must_belong_to_the_case(user_client: TestClient):
    case_a, _ = case_with_link(user_client)
    _case_b, (link_b,) = case_with_link(user_client, urls=("https://site.test/other",))
    setup_locker(user_client)
    assert add(user_client, case_a, link_id=link_b).status_code == 404


# ---------------- Timeline and overview ----------------

def test_timeline_merges_everything_newest_first(user_client: TestClient):
    case_id, (link_id,) = case_with_link(user_client)
    comp = template_complaint(user_client, link_id)
    move(user_client, comp["id"], "submitted_by_user")
    setup_locker(user_client)
    add(user_client, case_id, "note", link_id=link_id)
    items = user_client.get(f"/api/cases/{case_id}/timeline").json()
    types = {i["type"] for i in items}
    assert {"link", "complaint", "evidence"} <= types
    assert [i["at"] for i in items] == sorted((i["at"] for i in items), reverse=True)
    assert all("secret" not in json.dumps(i) for i in items)
    # A complaint step is listed once, not again as its mirrored link event.
    texts = [i["text"] for i in items]
    assert texts.count("Complaint: Submitted by you") == 1


def test_overview_counts(user_client: TestClient):
    case_id, (l1, l2) = case_with_link(user_client, urls=(URL, "https://site.test/b"))
    c1 = template_complaint(user_client, l1)
    move(user_client, c1["id"], "submitted_by_user")
    template_complaint(user_client, l2)
    draft(user_client, case_id, l2)  # assistant draft awaiting approval
    o = user_client.get("/api/overview").json()
    assert o["confirmed_incidents"] == 1 and o["cases"][0]["links"] == 2
    assert o["submitted"] == 1 and o["pending_responses"] == 1
    assert o["drafts"] == 2  # one approved template + one assistant draft
    assert o["approvals_waiting"] == 1

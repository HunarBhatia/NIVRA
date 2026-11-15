"""Automatic sending of approved notices (section 22.6). No real email or
network: emails go to the console sender, RDAP lookups are faked."""

import pytest
from fastapi.testclient import TestClient

from app.services import notify, sending
from tests.test_incidents import link_status, template_complaint

RDAP = {"entities": [{"roles": ["registrant"], "entities": [
    {"roles": ["abuse"], "vcardArray": ["vcard", [["version", {}, "text", "4.0"],
                                                  ["email", {}, "text", "Abuse@Host.Example"]]]}]}]}


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    notify.ConsoleSender.sent.clear()
    notify.ConsoleSender.reply_tos.clear()
    sending._cache.clear()
    monkeypatch.setattr(sending.socket, "gethostbyname", lambda host: "93.184.216.34")
    monkeypatch.setattr(sending, "fetch_rdap", lambda ip: RDAP)
    yield


def make(c: TestClient, url: str) -> tuple[str, str]:
    case = c.post("/api/cases", json={"category": "intimate", "display_name": "Priya Test",
                                      "urls": [url]}).json()
    return case["id"], case["links"][0]["id"]


def test_rdap_parsing_finds_the_abuse_email():
    assert sending._emails_with_role(RDAP, "abuse") == ["abuse@host.example"]
    assert sending._emails_with_role({"entities": []}, "abuse") == []


def test_unknown_site_is_emailed_to_its_host(user_client: TestClient):
    _case, link_id = make(user_client, "https://leaks.example/post/9")
    where = user_client.get(f"/api/links/{link_id}/recipients").json()
    assert where["emails"][0]["address"] == "abuse@host.example" and not where["form_only"]
    comp = template_complaint(user_client, link_id)
    r = user_client.post(f"/api/complaints/{comp['id']}/send")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "sent_by_nivra" and out["sent_to"] == ["abuse@host.example"]
    assert out["delivered"] is False  # development: console backend
    to, subject, body = notify.ConsoleSender.sent[0]
    assert to == "abuse@host.example" and "https://leaks.example/post/9" in body
    assert "Priya Test" in body and "{{" not in body
    assert link_status(link_id) == "reported"


def test_platform_email_channel_is_used(user_client: TestClient):
    _case, link_id = make(user_client, "https://t.me/leakchannel/5")
    comp = template_complaint(user_client, link_id)
    out = user_client.post(f"/api/complaints/{comp['id']}/send").json()
    assert out["sent_to"] == ["abuse@telegram.org"]


def test_form_only_platforms_are_not_emailed(user_client: TestClient):
    _case, link_id = make(user_client, "https://instagram.com/p/x")
    where = user_client.get(f"/api/links/{link_id}/recipients").json()
    assert where["form_only"] and where["forms"]
    comp = template_complaint(user_client, link_id)
    r = user_client.post(f"/api/complaints/{comp['id']}/send")
    assert r.status_code == 409 and "form" in r.json()["detail"]
    assert notify.ConsoleSender.sent == []


def test_needs_approval_and_sends_only_once(user_client: TestClient):
    case_id, link_id = make(user_client, "https://leaks.example/a")
    from tests.test_agents import draft
    run = draft(user_client, case_id, link_id).json()  # assistant draft, not approved
    cid = run["output"]["complaint_id"]
    assert user_client.post(f"/api/complaints/{cid}/send").status_code == 409
    user_client.post(f"/api/agents/runs/{run['id']}/decision", json={"decision": "approve"})
    assert user_client.post(f"/api/complaints/{cid}/send").status_code == 200
    assert user_client.post(f"/api/complaints/{cid}/send").status_code == 409


def test_replies_go_to_the_users_email(user_client: TestClient):
    user_client.patch("/api/account", json={"email": "me@example.com"})
    _case, link_id = make(user_client, "https://leaks.example/b")
    comp = template_complaint(user_client, link_id)
    out = user_client.post(f"/api/complaints/{comp['id']}/send").json()
    assert out["replies_to_you"] and notify.ConsoleSender.reply_tos[0] == "me@example.com"


def test_no_contact_found(user_client: TestClient, monkeypatch):
    monkeypatch.setattr(sending, "fetch_rdap", lambda ip: {"entities": []})
    _case, link_id = make(user_client, "https://nowhere.example/x")
    comp = template_complaint(user_client, link_id)
    r = user_client.post(f"/api/complaints/{comp['id']}/send")
    assert r.status_code == 409 and "couldn't find" in r.json()["detail"]


def test_private_addresses_are_never_looked_up(user_client: TestClient, monkeypatch):
    calls = []
    monkeypatch.setattr(sending.socket, "gethostbyname", lambda host: "10.0.0.5")
    monkeypatch.setattr(sending, "fetch_rdap", lambda ip: calls.append(ip) or RDAP)
    assert sending.host_abuse_email("internal.example") is None and calls == []

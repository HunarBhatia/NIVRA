import pytest
from fastapi.testclient import TestClient

from app.services.links import InvalidUrl, normalise_url
from tests.conftest import register


def new_case(c: TestClient, urls=None) -> dict:
    r = c.post("/api/cases", json={
        "category": "intimate", "self_taken": True, "display_name": "Test",
        "urls": urls if urls is not None else ["instagram.com/p/test1", "https://t.me/leaks/5"],
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_cases_require_login(client: TestClient):
    assert client.get("/api/cases").status_code == 401
    assert client.post("/api/cases", json={"category": "intimate"}).status_code == 401


def test_create_case_normalises_links(user_client: TestClient):
    case = new_case(user_client, ["instagram.com/p/test1", "not a link", "javascript:alert(1)",
                                  "https://www.t.me/x", "instagram.com/p/test1"])
    urls = [link["url"] for link in case["links"]]
    assert urls == ["https://instagram.com/p/test1", "https://www.t.me/x"]
    assert case["links"][1]["host"] == "t.me"
    assert all(link["status"] == "found" for link in case["links"])
    assert case["links"][0]["events"][0]["note"] == "Link added"


def test_list_and_get_case(user_client: TestClient):
    case = new_case(user_client)
    listed = user_client.get("/api/cases").json()
    assert listed == [{"id": case["id"], "category": "intimate",
                       "created_at": case["created_at"], "link_count": 2}]
    assert user_client.get(f"/api/cases/{case['id']}").json()["id"] == case["id"]


def test_other_accounts_cannot_see_or_change_a_case(client: TestClient):
    register(client)
    case = new_case(client)
    link_id = case["links"][0]["id"]
    client.post("/api/auth/logout")
    register(client)  # a second, different account
    assert client.get(f"/api/cases/{case['id']}").status_code == 404
    assert client.post(f"/api/cases/{case['id']}/links", json={"urls": ["x.com/a"]}).status_code == 404
    assert client.post(f"/api/links/{link_id}/status", json={"status": "reported"}).status_code == 404
    assert client.delete(f"/api/cases/{case['id']}").status_code == 404
    assert client.get("/api/cases").json() == []


def test_add_links_skips_duplicates(user_client: TestClient):
    case = new_case(user_client)
    r = user_client.post(f"/api/cases/{case['id']}/links",
                         json={"urls": ["instagram.com/p/test1", "x.com/someone/status/1"]})
    assert r.status_code == 200
    assert len(r.json()["links"]) == 3
    r = user_client.post(f"/api/cases/{case['id']}/links", json={"urls": ["instagram.com/p/test1"]})
    assert r.status_code == 400


def test_status_flow_and_history(user_client: TestClient):
    link = new_case(user_client)["links"][0]
    lid = link["id"]

    def move(status):
        return user_client.post(f"/api/links/{lid}/status", json={"status": status, "note": status})

    assert move("removed").status_code == 409  # can't skip reporting
    r = move("reported")
    assert r.status_code == 200 and r.json()["reported_at"]
    assert move("rejected").status_code == 200
    assert move("escalated").status_code == 200
    assert move("removed").status_code == 200
    r = move("reappeared")
    assert [e["status"] for e in r.json()["events"]] == [
        "found", "reported", "rejected", "escalated", "removed", "reappeared"]


def test_simulate_deadline_only_for_reported_links(user_client: TestClient):
    lid = new_case(user_client)["links"][0]["id"]
    assert user_client.post(f"/api/links/{lid}/simulate-deadline").status_code == 409
    user_client.post(f"/api/links/{lid}/status", json={"status": "reported"})
    r = user_client.post(f"/api/links/{lid}/simulate-deadline")
    assert r.status_code == 200 and r.json()["deadline_override"] is True
    # Reporting again resets the override.
    user_client.post(f"/api/links/{lid}/status", json={"status": "rejected"})
    r = user_client.post(f"/api/links/{lid}/status", json={"status": "reported"})
    assert r.json()["deadline_override"] is False


def test_update_and_delete_case(user_client: TestClient):
    case = new_case(user_client)
    r = user_client.patch(f"/api/cases/{case['id']}", json={"display_name": "  New Name "})
    assert r.json()["display_name"] == "New Name"
    assert user_client.delete(f"/api/cases/{case['id']}").status_code == 204
    assert user_client.get(f"/api/cases/{case['id']}").status_code == 404


def test_unknown_fields_rejected(user_client: TestClient):
    r = user_client.post("/api/cases", json={"category": "intimate", "user_id": "someone-else"})
    assert r.status_code == 422


@pytest.mark.parametrize("raw,expected", [
    ("instagram.com/p/x", ("https://instagram.com/p/x", "instagram.com")),
    ("http://WWW.Example.org/a", ("http://WWW.Example.org/a", "example.org")),
])
def test_normalise_url_accepts(raw, expected):
    assert normalise_url(raw) == expected


@pytest.mark.parametrize("raw", [
    "", "hello", "ftp://example.com/a", "javascript:alert(1)", "https://user:pw@example.com",
    "https://exa mple.com", "https://localhost/x", "x" * 3000 + ".com",
])
def test_normalise_url_rejects(raw):
    with pytest.raises(InvalidUrl):
        normalise_url(raw)

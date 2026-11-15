"""Bundled demo sites and "check first, then draft" (section 23).

The demo sites are served from files, so these tests run the REAL scanner,
matching, auto-drafting and sending end to end without any network."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.demo_sites import FILES, serve_demo
from app.discovery.fetch import FetchError
from app.discovery.jobs import process_job
from app.discovery.providers import UserSubmittedUrlProvider
from app.fingerprint.compare import sha256_hex
from app.fingerprint.phash import phash_image
from app.services import notify
from tests.test_incidents import template_complaint

PHOTO = (FILES / "dump_exact.jpg").read_bytes()  # the demo's protected photo
SNAP = "https://snapgram.test/p/Cx8LqP2"
BLOG = "https://travelblog.test/2026/lakes-of-the-north"
PRIVATE = "https://privategroup.test/g/hidden-album"


def test_demo_sites_are_served_from_files():
    page = serve_demo(SNAP, 10_000_000)
    assert page.content_type == "text/html" and b"snap_post.jpg" in page.body
    img = serve_demo("https://imgdump.test/i/9f3k2.jpg", 10_000_000)
    assert img.content_type == "image/jpeg" and img.body == PHOTO
    with pytest.raises(FetchError) as blocked:
        serve_demo(PRIVATE, 10_000_000)
    assert blocked.value.code == "forbidden"
    with pytest.raises(FetchError):
        serve_demo("https://snapgram.test/nope", 10_000_000)
    assert serve_demo("https://other.test/page", 10_000_000) is None  # normal fetch path


def test_demo_info_lists_the_sites(client: TestClient):
    info = client.get("/api/demo").json()
    assert info["enabled"] and len(info["links"]) == 5


def test_demo_thumbnails_only_for_demo_images(client: TestClient):
    ok = client.get("/api/demo/image", params={"url": "https://snapgram.test/media/snap_post.jpg"})
    assert ok.status_code == 200 and ok.headers["content-type"] == "image/jpeg"
    assert client.get("/api/demo/image", params={"url": SNAP}).status_code == 404  # a page
    assert client.get("/api/demo/image", params={"url": "https://example.com/a.jpg"}).status_code == 404


def run(job_id: str):
    with SessionLocal() as db:
        return process_job(db, job_id, providers={"user_url": UserSubmittedUrlProvider(delay_seconds=0)})


def test_check_first_then_draft_with_evidence(user_client: TestClient):
    c = user_client
    r = c.post("/api/images", json={
        "label": "Photo from my case", "consent_version": "2026-11-v1",
        "consent": {"subject_is_adult": True, "is_subject_or_authorised": True},
        "fingerprints": {"sha256": sha256_hex(PHOTO), "phash": phash_image(PHOTO)}})
    assert r.status_code == 201, r.text
    case = c.post("/api/cases", json={"category": "intimate", "display_name": "Demo User",
                                      "urls": [SNAP, BLOG, PRIVATE]}).json()
    links = {lk["url"]: lk["id"] for lk in case["links"]}
    for url, link_id in links.items():
        job = c.post("/api/discovery/jobs", json={"url": url, "link_id": link_id})
        assert job.status_code == 202 and job.json()["case_link_id"] == link_id
        run(job.json()["id"])

    scans = c.get(f"/api/cases/{case['id']}/scans").json()
    assert scans[links[SNAP]]["best"] == "high" and scans[links[SNAP]]["matches_found"] == 1
    assert scans[links[BLOG]]["best"] == "none"  # a different lake photo is not a match
    assert scans[links[PRIVATE]]["status"] == "failed"

    complaints = {x["link_id"]: x for x in c.get(f"/api/cases/{case['id']}/complaints").json()}
    snap = complaints[links[SNAP]]
    assert snap["status"] == "draft_generated"
    assert "automated image-fingerprint check" in snap["body"] and "of 64 points" in snap["body"]
    assert links[BLOG] not in complaints  # photo not found: the user decides, no draft
    private = complaints[links[PRIVATE]]  # couldn't check: drafted, but claims nothing
    assert "fingerprint" not in private["body"]

    # Re-checking a link that already has a notice doesn't draft a second one.
    again = c.post("/api/discovery/jobs", json={"url": SNAP, "link_id": links[SNAP]}).json()
    run(again["id"])
    assert len([x for x in c.get(f"/api/cases/{case['id']}/complaints").json()
                if x["link_id"] == links[SNAP]]) == 1


def test_someone_elses_link_is_refused(client: TestClient, user_client: TestClient):
    r = user_client.post("/api/discovery/jobs", json={"url": SNAP, "link_id": "x" * 32})
    assert r.status_code in (400, 404)


def test_sender_details_and_demo_redirect(user_client: TestClient, monkeypatch):
    c = user_client
    case = c.post("/api/cases", json={"category": "intimate", "display_name": "Demo User",
                                      "urls": [SNAP]}).json()
    link_id = case["links"][0]["id"]
    where = c.get(f"/api/links/{link_id}/recipients").json()
    assert where["emails"][0]["address"] == "abuse@snapgram.test"
    assert where["from_address"] == get_settings().smtp_from and where["delivery"] == "console"

    notify.ConsoleSender.sent.clear()
    monkeypatch.setattr(get_settings(), "email_redirect_to", "presenter@example.org")
    comp = template_complaint(c, link_id)
    sent = c.post(f"/api/complaints/{comp['id']}/send").json()
    assert sent["sent_to"] == ["abuse@snapgram.test"] and sent["redirect_to"] == "presenter@example.org"
    to, subject, body = notify.ConsoleSender.sent[-1]
    assert to == "presenter@example.org" and "abuse@snapgram.test" in subject
    assert "in real use this notice goes to abuse@snapgram.test" in body

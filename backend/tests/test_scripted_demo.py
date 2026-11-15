"""Scripted demo pages (section 24): a blocked real URL served from a local
copy for demonstrations. Uses a temporary scripts folder, not the real one."""

import json
import shutil

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.demo_sites import FILES, scripted
from tests.test_demo_flow import PHOTO, run

URL = "https://www.blockednews.example/gallery/photo-7.html"


@pytest.fixture
def scripts(tmp_path, monkeypatch):
    shutil.copy(FILES / "snap_post.jpg", tmp_path / "copy.jpg")  # an edited copy of PHOTO
    shutil.copy(FILES / "city.jpg", tmp_path / "filler.jpg")
    (tmp_path / "scripts.json").write_text(json.dumps({"pages": [
        {"url": URL, "title": "Gallery (scripted)", "images": ["filler.jpg", "copy.jpg"]}]}))
    monkeypatch.setattr(scripted, "SCRIPTS_DIR", tmp_path)
    scripted._cache.update(mtime=None, pages=[])
    yield
    scripted._cache.update(mtime=None, pages=[])


def protect(c: TestClient, data: bytes):
    from app.fingerprint.compare import sha256_hex
    from app.fingerprint.phash import phash_image
    r = c.post("/api/images", json={
        "label": "Mine", "consent_version": "2026-11-v1",
        "consent": {"subject_is_adult": True, "is_subject_or_authorised": True},
        "fingerprints": {"sha256": sha256_hex(data), "phash": phash_image(data)}})
    assert r.status_code == 201, r.text


def test_scripted_page_is_served_and_matched_for_real(scripts, user_client: TestClient):
    assert scripted.is_scripted_url("http://blockednews.example/gallery/photo-7.html/")  # www/slash-insensitive
    protect(user_client, PHOTO)
    case = user_client.post("/api/cases", json={"category": "intimate", "urls": [URL]}).json()
    link_id = case["links"][0]["id"]
    job = user_client.post("/api/discovery/jobs", json={"url": URL, "link_id": link_id}).json()
    done = run(job["id"])
    assert done.status == "done" and done.page_title == "Gallery (scripted)"
    results = [e["result"] for e in done.scan_log]
    assert results == ["none", "high"] and all(e["scripted"] for e in done.scan_log)
    assert user_client.get(f"/api/cases/{case['id']}/scans").json()[link_id]["scripted"] is True


def test_other_photos_do_not_match_a_scripted_page(scripts, user_client: TestClient):
    protect(user_client, (FILES / "blog_lake.jpg").read_bytes())  # a different photo
    job = user_client.post("/api/discovery/jobs", json={"url": URL}).json()
    assert run(job["id"]).matches_found == 0


def test_real_delivery_is_refused_for_scripted_links(scripts, user_client: TestClient, monkeypatch):
    from tests.test_incidents import template_complaint
    case = user_client.post("/api/cases", json={"category": "intimate", "urls": [URL]}).json()
    comp = template_complaint(user_client, case["links"][0]["id"])
    monkeypatch.setattr(get_settings(), "email_backend", "smtp")
    r = user_client.post(f"/api/complaints/{comp['id']}/send")
    assert r.status_code == 409 and "scripted demo" in r.json()["detail"]


def test_off_when_demo_sites_disabled(scripts, monkeypatch):
    monkeypatch.setattr(get_settings(), "enable_demo_sites", False)
    assert not scripted.is_scripted_url(URL)
    assert scripted.serve_scripted(URL, 10_000_000) is None

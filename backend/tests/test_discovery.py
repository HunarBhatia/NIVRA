"""Discovery: safe fetching, page parsing, matching jobs, review, worker.

No real network: a mock transport plays the websites, and a fake resolver
maps hostnames to (pretend) public or private IPs.
"""

from io import BytesIO

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.core.db import SessionLocal
from app.discovery.fetch import FetchError, SafeFetcher, is_public_ip
from app.discovery.jobs import process_job
from app.discovery.matching import fingerprint_candidate
from app.discovery.parse import extract_image_urls
from app.discovery.providers import UserSubmittedUrlProvider
from app.discovery.worker import claim_next, recover_stale
from app.fingerprint.compare import sha256_hex
from app.fingerprint.phash import phash_image
from app.models import DiscoveredMatch, DiscoveryJob
from tests.conftest import PASS, register
from tests.test_fingerprint import encode, photo

PUBLIC = {"site.test": "93.184.216.34", "cdn.test": "151.101.1.1", "evil.test": "10.0.0.5"}


def resolver(host: str) -> list[str]:
    if host not in PUBLIC:
        raise FetchError("dns", "not found")
    return [PUBLIC[host]]


class Web:
    """A tiny fake internet keyed by (Host header, path)."""

    def __init__(self, pages: dict[tuple[str, str], httpx.Response]):
        self.pages = pages
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        key = (request.headers["host"], request.url.path)
        if key in self.pages:
            return self.pages[key]
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(404)


def fetcher(pages, **kw) -> tuple[SafeFetcher, Web]:
    web = Web(pages)
    return SafeFetcher(resolver=resolver, allow_private=False,
                       transport=httpx.MockTransport(web), **kw), web


def img_response(data: bytes, ctype="image/png") -> httpx.Response:
    return httpx.Response(200, content=data, headers={"content-type": ctype})


def html(body: str) -> httpx.Response:
    return httpx.Response(200, text=body, headers={"content-type": "text/html; charset=utf-8"})


# ---------------- Safe fetcher ----------------

@pytest.mark.parametrize("ip,public", [
    ("93.184.216.34", True), ("10.0.0.1", False), ("127.0.0.1", False), ("169.254.169.254", False),
    ("192.168.1.1", False), ("100.64.0.1", False), ("::1", False), ("fd00::1", False),
    ("::ffff:127.0.0.1", False), ("2606:4700::1111", True), ("0.0.0.0", False),
])
def test_is_public_ip(ip, public):
    assert is_public_ip(ip) is public


def test_private_addresses_refused():
    f, web = fetcher({})
    for url in ["https://evil.test/x", "http://127.0.0.1/", "http://[::1]/", "http://169.254.169.254/latest"]:
        with pytest.raises(FetchError) as e:
            f.get(url, 1000)  # robots.txt checking on: the address check still comes first
        assert e.value.code == "private"
    assert web.seen == []  # nothing was ever sent, not even a robots.txt request


def test_bad_scheme_and_port_refused():
    f, _ = fetcher({})
    with pytest.raises(FetchError, match="http"):
        f.get("ftp://site.test/a", 1000)
    with pytest.raises(FetchError) as e:
        f.get("http://site.test:8080/a", 1000)
    assert e.value.code == "port"


def test_request_is_pinned_to_resolved_ip_with_real_host():
    f, web = fetcher({("site.test", "/a.png"): img_response(b"x")})
    f.get("https://site.test/a.png", 1000, check_robots=False)
    req = web.seen[0]
    assert req.url.host == "93.184.216.34"
    assert req.headers["host"] == "site.test"
    assert req.extensions.get("sni_hostname") == "site.test"
    assert "NivraBot" in req.headers["user-agent"]


def test_redirect_to_private_host_refused():
    f, _ = fetcher({("site.test", "/go"): httpx.Response(302, headers={"location": "https://evil.test/"})})
    with pytest.raises(FetchError) as e:
        f.get("https://site.test/go", 1000, check_robots=False)
    assert e.value.code == "private"


def test_too_many_redirects():
    loop = httpx.Response(302, headers={"location": "/go"})
    f, _ = fetcher({("site.test", "/go"): loop})
    with pytest.raises(FetchError) as e:
        f.get("https://site.test/go", 1000, check_robots=False)
    assert e.value.code == "redirect"


def test_size_limits():
    f, _ = fetcher({("site.test", "/big"): img_response(b"x" * 5000)})
    with pytest.raises(FetchError) as e:
        f.get("https://site.test/big", 1000, check_robots=False)
    assert e.value.code == "too_large"


def test_login_walls_are_respected():
    f, _ = fetcher({("site.test", "/private"): httpx.Response(403)})
    with pytest.raises(FetchError) as e:
        f.get("https://site.test/private", 1000)
    assert e.value.code == "forbidden"


def test_robots_txt_rules():
    robots = httpx.Response(200, text="User-agent: *\nDisallow: /nope/\n")
    f, _ = fetcher({("site.test", "/robots.txt"): robots, ("site.test", "/ok.png"): img_response(b"x")})
    assert f.get("https://site.test/ok.png", 1000).status == 200
    with pytest.raises(FetchError) as e:
        f.get("https://site.test/nope/a.png", 1000)
    assert e.value.code == "robots"
    # A server error on robots.txt means: be cautious, don't crawl.
    f2, _ = fetcher({("site.test", "/robots.txt"): httpx.Response(503),
                     ("site.test", "/ok.png"): img_response(b"x")})
    with pytest.raises(FetchError):
        f2.get("https://site.test/ok.png", 1000)


# ---------------- Page parsing ----------------

def test_extract_image_urls():
    page = """<html><head><title> My page </title>
      <meta property="og:image" content="/og.jpg"></head><body>
      <img src="a.png"><img srcset="small.jpg 320w, large.jpg 1280w" src="small.jpg">
      <img src="data:image/png;base64,AAAA"><img data-src="https://cdn.test/lazy.webp">
      <img src="a.png"></body></html>"""
    urls, title = extract_image_urls(page, "https://site.test/posts/1")
    assert title == "My page"
    assert urls == ["https://site.test/og.jpg", "https://site.test/posts/a.png",
                    "https://site.test/posts/large.jpg", "https://site.test/posts/small.jpg",
                    "https://cdn.test/lazy.webp"]


def test_decompression_bomb_refused():
    huge = Image.new("1", (7000, 7000))  # 49M pixels: above our 40M limit
    assert fingerprint_candidate(encode(huge)) is None
    assert fingerprint_candidate(b"not an image") is None


# ---------------- Jobs end to end ----------------

ORIGINAL = encode(photo(7))
RESIZED = encode(photo(7).resize((320, 240)), "JPEG", quality=55)
OTHER = encode(photo(107))


def protect(client: TestClient, data: bytes = ORIGINAL, label="Mine") -> str:
    r = client.post("/api/images", json={
        "label": label, "consent": {"subject_is_adult": True, "is_subject_or_authorised": True},
        "consent_version": "2026-11-v1",
        "fingerprints": {"sha256": sha256_hex(data), "phash": phash_image(data)}})
    assert r.status_code == 201, r.text
    return r.json()["id"]


PAGE = """<html><head><title>Leak thread</title></head><body>
  <img src="/1.png"><img src="https://cdn.test/2.jpg"><img src="/3.png">
  <img src="/icon.svg"><img src="/gone.png"></body></html>"""


def site():
    return {
        ("site.test", "/thread"): html(PAGE),
        ("site.test", "/1.png"): img_response(ORIGINAL),
        ("cdn.test", "/2.jpg"): img_response(RESIZED, "image/jpeg"),
        ("site.test", "/3.png"): img_response(OTHER),
        ("site.test", "/icon.svg"): img_response(b"<svg/>", "image/svg+xml"),
    }


def run(job_id: str, pages=None) -> DiscoveryJob:
    f, _ = fetcher(pages or site())
    with SessionLocal() as db:
        return process_job(db, job_id, fetcher=f,
                           providers={"user_url": UserSubmittedUrlProvider(delay_seconds=0)})


def test_job_finds_exact_and_resized_copies(user_client: TestClient):
    protect(user_client)
    job = user_client.post("/api/discovery/jobs", json={"url": "site.test/thread"})
    assert job.status_code == 202 and job.json()["status"] == "queued"
    done = run(job.json()["id"])
    assert done.status == "done" and done.page_title == "Leak thread"
    assert (done.candidates_found, done.candidates_checked, done.candidates_skipped) == (5, 3, 2)
    assert done.matches_found == 2
    matches = user_client.get("/api/matches").json()
    by_url = {m["candidate_image_url"]: m for m in matches}
    assert by_url["https://site.test/1.png"]["classification"] == "exact"
    assert by_url["https://cdn.test/2.jpg"]["classification"] == "high"
    assert all(m["status"] == "pending" and m["source_page_url"] == "https://site.test/thread"
               for m in matches)
    assert "https://site.test/3.png" not in by_url  # different image: not stored at all


def test_rerun_keeps_review_and_does_not_duplicate(user_client: TestClient):
    protect(user_client)
    jid = user_client.post("/api/discovery/jobs", json={"url": "https://site.test/thread"}).json()["id"]
    run(jid)
    first = user_client.get("/api/matches").json()[0]
    user_client.post(f"/api/matches/{first['id']}/review", json={"decision": "rejected"})
    jid2 = user_client.post("/api/discovery/jobs", json={"url": "https://site.test/thread"}).json()["id"]
    run(jid2)
    matches = user_client.get("/api/matches").json()
    assert len(matches) == 2
    assert {m["id"]: m["status"] for m in matches}[first["id"]] == "rejected"


def test_paused_images_are_not_matched(user_client: TestClient):
    image_id = protect(user_client)
    protect(user_client, OTHER, "Other")  # keep one active so the job is allowed
    user_client.patch(f"/api/images/{image_id}", json={"status": "paused"})
    jid = user_client.post("/api/discovery/jobs", json={"url": "https://site.test/thread"}).json()["id"]
    run(jid)
    labels = {m["image_label"] for m in user_client.get("/api/matches").json()}
    assert labels == {"Other"}


def test_failed_page_gives_a_safe_message(user_client: TestClient):
    protect(user_client)
    jid = user_client.post("/api/discovery/jobs", json={"url": "https://site.test/missing"}).json()["id"]
    done = run(jid)
    assert done.status == "failed" and done.error_code == "not_found"
    out = user_client.get(f"/api/discovery/jobs/{jid}").json()
    assert out["status"] == "failed" and "removed" in out["error_message"]


def test_direct_image_link(user_client: TestClient):
    protect(user_client)
    jid = user_client.post("/api/discovery/jobs", json={"url": "https://site.test/1.png"}).json()["id"]
    assert run(jid).matches_found == 1


def test_job_rules(user_client: TestClient):
    r = user_client.post("/api/discovery/jobs", json={"url": "https://site.test/thread"})
    assert r.status_code == 400  # nothing protected yet
    protect(user_client)
    assert user_client.post("/api/discovery/jobs", json={"url": "javascript:alert(1)"}).status_code == 422
    from app.api import discovery
    old = discovery.settings.discovery_jobs_per_hour
    discovery.settings.discovery_jobs_per_hour = 2
    try:
        codes = [user_client.post("/api/discovery/jobs", json={"url": "https://site.test/a"}).status_code
                 for _ in range(3)]
    finally:
        discovery.settings.discovery_jobs_per_hour = old
    assert codes == [202, 202, 429]


# ---------------- Review and cases ----------------

def found_match(client: TestClient) -> dict:
    protect(client)
    jid = client.post("/api/discovery/jobs", json={"url": "https://site.test/thread"}).json()["id"]
    run(jid)
    return client.get("/api/matches").json()[0]


def test_review_then_add_to_new_case(user_client: TestClient):
    m = found_match(user_client)
    r = user_client.post(f"/api/matches/{m['id']}/add-to-case", json={"category": "intimate"})
    assert r.status_code == 409  # must be confirmed first
    user_client.post(f"/api/matches/{m['id']}/review", json={"decision": "confirmed"})
    r = user_client.post(f"/api/matches/{m['id']}/add-to-case", json={"category": "intimate"})
    assert r.status_code == 200
    case = user_client.get(f"/api/cases/{r.json()['case_id']}").json()
    assert [link["url"] for link in case["links"]] == ["https://site.test/thread"]
    assert user_client.get("/api/matches?status_filter=confirmed").json()[0]["case_link_id"]


def test_add_to_existing_case_without_duplicates(user_client: TestClient):
    m = found_match(user_client)
    user_client.post(f"/api/matches/{m['id']}/review", json={"decision": "confirmed"})
    case_id = user_client.post("/api/cases", json={
        "category": "intimate", "urls": ["https://site.test/thread"]}).json()["id"]
    r = user_client.post(f"/api/matches/{m['id']}/add-to-case", json={"case_id": case_id})
    assert r.status_code == 200
    assert len(user_client.get(f"/api/cases/{case_id}").json()["links"]) == 1


def test_matches_are_private_to_their_account(client: TestClient):
    register(client)
    m = found_match(client)
    client.post("/api/auth/logout")
    register(client)
    assert client.get("/api/matches").json() == []
    assert client.get("/api/discovery/jobs").json() == []
    assert client.post(f"/api/matches/{m['id']}/review", json={"decision": "confirmed"}).status_code == 404
    assert client.post(f"/api/matches/{m['id']}/add-to-case", json={"category": "intimate"}).status_code == 404


def test_account_deletion_removes_jobs_and_matches(user_client: TestClient):
    found_match(user_client)
    user_client.request("DELETE", "/api/account", json={"passphrase": PASS})
    with SessionLocal() as db:
        assert db.scalar(select(DiscoveredMatch)) is None
        assert db.scalar(select(DiscoveryJob)) is None


# ---------------- Worker ----------------

def test_worker_claims_each_job_once(user_client: TestClient):
    protect(user_client)
    jid = user_client.post("/api/discovery/jobs", json={"url": "https://site.test/thread"}).json()["id"]
    assert claim_next() == jid
    assert claim_next() is None
    # A job stuck in 'running' (crashed worker, never started) is re-queued.
    recover_stale()
    assert claim_next() == jid


def test_candidate_bytes_never_stored(user_client: TestClient):
    found_match(user_client)
    with SessionLocal() as db:
        for m in db.scalars(select(DiscoveredMatch)):
            for value in vars(m).values():
                assert not isinstance(value, (bytes, bytearray))
    assert BytesIO  # (imports used)


def test_scan_log_records_each_image_without_storing_it(user_client: TestClient):
    protect(user_client)
    jid = user_client.post("/api/discovery/jobs", json={"url": "https://site.test/thread"}).json()["id"]
    run(jid)
    job = user_client.get(f"/api/discovery/jobs/{jid}").json()
    assert job["stage"] == "done"
    log = {e["url"]: e for e in job["scan_log"]}
    exact = log["https://site.test/1.png"]
    assert exact["result"] == "exact" and exact["diff"] == "0" * 16 and len(exact["phash"]) == 16
    assert log["https://cdn.test/2.jpg"]["result"] == "high"
    assert log["https://site.test/3.png"]["result"] == "none"
    assert log["https://site.test/3.png"]["distance"] > 12

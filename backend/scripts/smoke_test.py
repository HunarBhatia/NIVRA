"""End-to-end smoke test against a RUNNING Nivra (website + API), section 21.10.

Goes through the website's /api proxy exactly like a browser: registers a
throwaway account, opens a case, tracks a complaint, checks the timeline and
overview, then deletes the account. Leaves nothing behind.

  .venv/Scripts/python scripts/smoke_test.py                       # local dev
  .venv/Scripts/python scripts/smoke_test.py https://nivra.example.org

Exit code 0 = every step passed.
"""

import secrets
import sys

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000").rstrip("/")
PASS = "smoke-" + secrets.token_urlsafe(12)


def step(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {name}{f' - {detail}' if detail and not ok else ''}")
    if not ok:
        raise SystemExit(1)


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=30, headers={"Origin": BASE}) as c:
        r = c.get("/api/health")
        step("API reachable through the website", r.status_code == 200, r.text[:120])
        r = c.get("/api/ready")
        step("API ready (database, storage, platforms)", r.status_code == 200, r.text[:200])
        r = c.get("/")
        csp = r.headers.get("content-security-policy", "")
        step("Website serves security headers", r.status_code == 200 and "frame-ancestors 'none'" in csp)

        r = c.post("/api/auth/register", json={"passphrase": PASS})
        step("Register a throwaway account", r.status_code == 201, r.text[:120])
        step("Session cookie is httpOnly", "httponly" in r.headers.get("set-cookie", "").lower())

        r = c.post("/api/cases", json={"category": "intimate", "urls": ["https://instagram.com/p/smoke-test"]})
        step("Create a case with a link", r.status_code == 201, r.text[:120])
        case = r.json()
        link_id = case["links"][0]["id"]

        r = c.post(f"/api/links/{link_id}/complaints", json={
            "subject": "Smoke test notice", "body": "Please remove {{URL}} - smoke test. " * 3})
        step("Track a complaint", r.status_code == 201, r.text[:120])
        cid = r.json()["id"]
        r = c.post(f"/api/complaints/{cid}/status", json={"status": "submitted_by_user"})
        step("Record it as submitted", r.status_code == 200 and r.json()["status"] == "submitted_by_user")
        r = c.get(f"/api/cases/{case['id']}")
        step("Link status followed the complaint", r.json()["links"][0]["status"] == "reported")

        r = c.get(f"/api/cases/{case['id']}/timeline")
        step("Timeline lists what happened", r.status_code == 200 and len(r.json()) >= 2)
        r = c.get("/api/overview")
        step("Dashboard overview", r.status_code == 200 and r.json()["confirmed_incidents"] == 1)
        r = c.get("/api/agents/status")
        step("Assistant status", r.status_code == 200, r.text[:120])

        r = c.request("DELETE", "/api/account", json={"passphrase": PASS})
        step("Delete the account and all its data", r.status_code == 204, r.text[:120])
        r = c.get("/api/auth/me")
        step("Session ended after deletion", r.status_code == 401)
    print("All smoke checks passed.")


if __name__ == "__main__":
    main()

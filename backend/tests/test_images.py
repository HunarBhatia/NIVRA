"""Protected images API: only fingerprints in, strict ownership, revocation."""

import math

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Fingerprint, ProtectedImage
from tests.conftest import PASS, register

SHA = "a" * 64
PHASH = "f0ace1345e6e1c63"
CONSENT = {"subject_is_adult": True, "is_subject_or_authorised": True}


def unit(seed: float, dims=512) -> list[float]:
    v = [math.sin(seed * (i + 1)) for i in range(dims)]
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def body(sha=SHA, phash=PHASH, embedding=None, consent=CONSENT, label="Beach photo"):
    fp = {"sha256": sha, "phash": phash}
    if embedding is not None:
        fp["embedding"] = {"model": "clip-vit-base-patch32-q8", "vector": embedding}
    return {"label": label, "consent": consent, "consent_version": "2026-11-v1", "fingerprints": fp}


def test_images_require_login(client: TestClient):
    assert client.get("/api/images").status_code == 401
    assert client.post("/api/images", json=body()).status_code == 401


def test_register_stores_only_fingerprints(user_client: TestClient):
    r = user_client.post("/api/images", json=body(embedding=unit(0.3)))
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["status"] == "active" and out["label"] == "Beach photo"
    assert sorted(f["kind"] for f in out["fingerprints"]) == ["embedding", "phash", "sha256"]
    # Fingerprint values are never sent back to the browser.
    assert SHA not in r.text and PHASH not in r.text
    with SessionLocal() as db:
        fps = {f.kind: f for f in db.scalars(select(Fingerprint))}
    assert fps["sha256"].value == SHA and fps["phash"].algorithm == "phash-dct-v1"
    assert fps["embedding"].dims == 512
    assert math.isclose(math.sqrt(sum(x * x for x in fps["embedding"].vector)), 1, rel_tol=1e-4)


def test_consent_is_required(user_client: TestClient):
    r = user_client.post("/api/images", json=body(consent={"subject_is_adult": False,
                                                           "is_subject_or_authorised": True}))
    assert r.status_code == 422
    r = user_client.post("/api/images", json={**body(), "consent_version": "old"})
    assert r.status_code == 422


def test_bad_fingerprints_rejected(user_client: TestClient):
    assert user_client.post("/api/images", json=body(sha="xyz")).status_code == 422
    assert user_client.post("/api/images", json=body(phash="F0ACE1345E6E1C63")).status_code == 422
    assert user_client.post("/api/images", json=body(embedding=unit(1, dims=64))).status_code == 422
    bad_model = body()
    bad_model["fingerprints"]["embedding"] = {"model": "some-other-model", "vector": unit(1)}
    assert user_client.post("/api/images", json=bad_model).status_code == 422
    # No way to smuggle image bytes in.
    extra = body()
    extra["fingerprints"]["image_base64"] = "iVBORw0KGgo="
    assert user_client.post("/api/images", json=extra).status_code == 422


def test_duplicate_exact_image_rejected(user_client: TestClient):
    assert user_client.post("/api/images", json=body()).status_code == 201
    assert user_client.post("/api/images", json=body()).status_code == 409


def test_pause_resume_and_relabel(user_client: TestClient):
    image_id = user_client.post("/api/images", json=body()).json()["id"]
    r = user_client.patch(f"/api/images/{image_id}", json={"status": "paused", "label": " New "})
    assert r.json()["status"] == "paused" and r.json()["label"] == "New"
    r = user_client.patch(f"/api/images/{image_id}", json={"status": "active"})
    assert r.json()["status"] == "active"


def test_add_embedding_later(user_client: TestClient):
    image_id = user_client.post("/api/images", json=body()).json()["id"]
    r = user_client.put(f"/api/images/{image_id}/embedding",
                        json={"model": "clip-vit-base-patch32-q8", "vector": unit(0.5)})
    assert "embedding" in [f["kind"] for f in r.json()["fingerprints"]]
    r = user_client.put(f"/api/images/{image_id}/embedding",
                        json={"model": "clip-vit-base-patch32-q8", "vector": unit(0.6)})
    assert [f["kind"] for f in r.json()["fingerprints"]].count("embedding") == 1


def test_revoke_deletes_fingerprints(user_client: TestClient):
    image_id = user_client.post("/api/images", json=body(embedding=unit(0.2))).json()["id"]
    assert user_client.delete(f"/api/images/{image_id}").status_code == 204
    assert user_client.get("/api/images").json() == []
    with SessionLocal() as db:
        assert db.scalar(select(Fingerprint)) is None


def test_check_copy_classifies_against_own_images(user_client: TestClient):
    user_client.post("/api/images", json=body(embedding=unit(0.3), label="One"))
    user_client.post("/api/images", json=body(sha="b" * 64, phash="0000000000000000", label="Two"))

    exact = user_client.post("/api/images/check", json={"sha256": SHA, "phash": PHASH}).json()
    assert exact["results"][0]["classification"] == "exact"
    assert exact["results"][0]["label"] == "One"

    near = user_client.post("/api/images/check",
                            json={"sha256": "c" * 64, "phash": "f0ace1345e6e1c60"}).json()
    assert near["results"][0]["classification"] == "high"
    assert near["results"][0]["phash_distance"] == 2

    by_embedding = user_client.post("/api/images/check", json={
        "sha256": "c" * 64, "phash": "ffffffffffffffff",
        "embedding": {"model": "clip-vit-base-patch32-q8", "vector": unit(0.3)}}).json()
    top = by_embedding["results"][0]
    # Embedding alone is only ever a "possible" (CLIP is semantic, not identity).
    assert top["classification"] == "possible" and top["cosine"] > 0.99


def test_other_accounts_cannot_touch_images(client: TestClient):
    register(client)
    image_id = client.post("/api/images", json=body()).json()["id"]
    client.post("/api/auth/logout")
    register(client)
    assert client.get("/api/images").json() == []
    assert client.patch(f"/api/images/{image_id}", json={"status": "paused"}).status_code == 404
    assert client.delete(f"/api/images/{image_id}").status_code == 404
    assert client.put(f"/api/images/{image_id}/embedding",
                      json={"model": "clip-vit-base-patch32-q8", "vector": unit(1)}).status_code == 404
    # Checking a copy only ever compares against your own images.
    r = client.post("/api/images/check", json={"sha256": SHA, "phash": PHASH})
    assert r.json()["results"] == []
    # And the same exact image can be protected by a different account.
    assert client.post("/api/images", json=body()).status_code == 201


def test_account_deletion_removes_protected_images(user_client: TestClient):
    user_client.post("/api/images", json=body(embedding=unit(0.4)))
    assert user_client.request("DELETE", "/api/account", json={"passphrase": PASS}).status_code == 204
    with SessionLocal() as db:
        assert db.scalar(select(ProtectedImage)) is None
        assert db.scalar(select(Fingerprint)) is None

"""Protected images: register, list, pause/resume, revoke, and check a copy.

The server only ever receives fingerprints computed in the user's browser
(D13). No endpoint here accepts image bytes. Every query is scoped to the
logged-in account.
"""

import math

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser
from app.core.config import get_settings
from app.fingerprint.compare import Thresholds, compare
from app.models import Fingerprint, ProtectedImage, User
from app.schemas import (
    CONSENT_VERSION,
    EmbeddingIn,
    MatchCheckIn,
    MatchCheckOut,
    MatchResultOut,
    ProtectedImageCreateIn,
    ProtectedImageOut,
    ProtectedImageUpdateIn,
)
from app.services import audit

router = APIRouter(prefix="/api/images", tags=["protected images"])
settings = get_settings()
NOT_FOUND = "We couldn't find that."


def thresholds() -> Thresholds:
    return Thresholds(
        phash_high=settings.phash_high_distance,
        phash_possible=settings.phash_possible_distance,
        cosine_high=settings.cosine_high,
        cosine_possible=settings.cosine_possible,
    )


def _own_image(db: DB, user: User, image_id: str) -> ProtectedImage:
    image = db.scalar(
        select(ProtectedImage).where(ProtectedImage.id == image_id, ProtectedImage.user_id == user.id)
    )
    if not image:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return image


def _embedding_fingerprint(e: EmbeddingIn) -> Fingerprint:
    if e.model not in settings.allowed_embedding_models:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That embedding model isn't supported.")
    if len(e.vector) != settings.embedding_dims:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The embedding has the wrong size.")
    norm = math.sqrt(sum(x * x for x in e.vector))
    if norm == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The embedding is empty.")
    unit = [round(x / norm, 6) for x in e.vector]
    return Fingerprint(kind="embedding", algorithm=e.model, vector=unit, dims=len(unit))


def _fp(image: ProtectedImage, kind: str) -> Fingerprint | None:
    return next((f for f in image.fingerprints if f.kind == kind), None)


@router.post("", response_model=ProtectedImageOut, status_code=201)
def register_image(body: ProtectedImageCreateIn, user: CurrentUser, db: DB) -> ProtectedImage:
    if not (body.consent.subject_is_adult and body.consent.is_subject_or_authorised):
        # The website routes under-18 cases to Take It Down before this point.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Nivra can only protect images of adults that are of you, or that you're authorised "
            "to act for.",
        )
    count = db.scalar(
        select(func.count(ProtectedImage.id)).where(ProtectedImage.user_id == user.id)
    ) or 0
    if count >= settings.max_protected_images_per_account:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You've reached the limit of protected images.")

    fp = body.fingerprints
    duplicate = db.scalar(
        select(Fingerprint.id).join(ProtectedImage)
        .where(ProtectedImage.user_id == user.id, Fingerprint.kind == "sha256",
               Fingerprint.value == fp.sha256)
    )
    if duplicate:
        raise HTTPException(status.HTTP_409_CONFLICT, "You've already protected this exact image.")

    image = ProtectedImage(
        user_id=user.id, label=body.label.strip(), consent_version=CONSENT_VERSION
    )
    image.fingerprints.append(Fingerprint(kind="sha256", algorithm="sha256", value=fp.sha256))
    image.fingerprints.append(Fingerprint(kind="phash", algorithm=fp.phash_algorithm, value=fp.phash))
    if fp.embedding:
        image.fingerprints.append(_embedding_fingerprint(fp.embedding))
    db.add(image)
    db.flush()
    audit.record(db, "image.registered", user.id, "protected_image", image.id)
    db.commit()
    return image


@router.get("", response_model=list[ProtectedImageOut])
def list_images(user: CurrentUser, db: DB) -> list[ProtectedImage]:
    return list(db.scalars(
        select(ProtectedImage).where(ProtectedImage.user_id == user.id)
        .order_by(ProtectedImage.created_at)
    ))


@router.patch("/{image_id}", response_model=ProtectedImageOut)
def update_image(image_id: str, body: ProtectedImageUpdateIn, user: CurrentUser, db: DB) -> ProtectedImage:
    image = _own_image(db, user, image_id)
    if body.label is not None:
        image.label = body.label.strip()
    if body.status is not None and body.status != image.status:
        image.status = body.status
        audit.record(db, f"image.{'paused' if body.status == 'paused' else 'resumed'}",
                     user.id, "protected_image", image.id)
    db.commit()
    return image


@router.put("/{image_id}/embedding", response_model=ProtectedImageOut)
def set_embedding(image_id: str, body: EmbeddingIn, user: CurrentUser, db: DB) -> ProtectedImage:
    """Adds (or replaces) the AI similarity fingerprint later, e.g. if the
    user skipped the model download when registering."""
    image = _own_image(db, user, image_id)
    new = _embedding_fingerprint(body)
    old = _fp(image, "embedding")
    if old:
        image.fingerprints.remove(old)
        db.flush()
    image.fingerprints.append(new)
    audit.record(db, "image.embedding_set", user.id, "protected_image", image.id)
    db.commit()
    return image


@router.delete("/{image_id}", status_code=204)
def revoke_image(image_id: str, user: CurrentUser, db: DB) -> Response:
    """Revokes protection: deletes the record and all its fingerprints."""
    image = _own_image(db, user, image_id)
    audit.record(db, "image.revoked", user.id, "protected_image", image.id)
    db.delete(image)
    db.commit()
    return Response(status_code=204)


@router.post("/check", response_model=MatchCheckOut)
def check_copy(body: MatchCheckIn, user: CurrentUser, db: DB) -> MatchCheckOut:
    """Compares a copy's fingerprints with the user's OWN protected images.
    Results are suggestions for the user to review - never a verdict."""
    emb_vector: list[float] | None = None
    if body.embedding and body.embedding.model in settings.allowed_embedding_models:
        emb_vector = body.embedding.vector
    t = thresholds()
    results = []
    for image in list_images(user, db):
        sha, ph, emb = _fp(image, "sha256"), _fp(image, "phash"), _fp(image, "embedding")
        same_model = emb and body.embedding and emb.algorithm == body.embedding.model
        c = compare(
            sha_a=sha.value if sha else None, sha_b=body.sha256,
            phash_a=ph.value if ph else None, phash_b=body.phash,
            emb_a=emb.vector if same_model else None, emb_b=emb_vector if same_model else None,
            t=t,
        )
        results.append(MatchResultOut(
            image_id=image.id, label=image.label, classification=c.classification,
            sha256_equal=c.sha256_equal, phash_distance=c.phash_distance, cosine=c.cosine,
        ))
    order = {"exact": 0, "high": 1, "possible": 2, "none": 3}
    results.sort(key=lambda r: (order[r.classification], r.phash_distance or 64))
    return MatchCheckOut(results=results, thresholds={
        "phash_high": t.phash_high, "phash_possible": t.phash_possible,
        "cosine_high": t.cosine_high, "cosine_possible": t.cosine_possible,
    })

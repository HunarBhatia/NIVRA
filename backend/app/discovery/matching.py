"""Fingerprint a candidate in memory and compare it with protected images."""

import warnings
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.fingerprint.compare import Comparison, Thresholds, compare, sha256_hex
from app.fingerprint.phash import gray32, phash_from_gray
from app.models import ProtectedImage

# Refuse "decompression bombs": tiny files that expand to enormous images.
Image.MAX_IMAGE_PIXELS = 40_000_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "BMP"}


@dataclass(frozen=True)
class CandidatePrints:
    sha256: str
    phash: str


def fingerprint_candidate(data: bytes) -> CandidatePrints | None:
    """Returns None if the bytes aren't a safe, decodable image. The bytes are
    never written anywhere; the caller drops them after this call."""
    try:
        with warnings.catch_warnings():
            # Pillow only WARNS between 1x and 2x MAX_IMAGE_PIXELS; refuse those too.
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as img:
                if img.format not in ALLOWED_FORMATS:
                    return None
                img.load()
                return CandidatePrints(sha256_hex(data), phash_from_gray(gray32(img)))
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning,
            OSError, ValueError):
        return None


def match_candidate(
    db: Session, user_id: str, prints: CandidatePrints, t: Thresholds
) -> list[tuple[ProtectedImage, Comparison]]:
    """Compares with the user's ACTIVE protected images (paused ones are
    skipped). Only exact/high/possible results are returned.

    The server has no embedding model for candidates yet (16.10), so
    matching here uses SHA-256 and pHash.
    """
    images = db.scalars(
        select(ProtectedImage)
        .where(ProtectedImage.user_id == user_id, ProtectedImage.status == "active")
        .options(selectinload(ProtectedImage.fingerprints))
    ).all()
    hits = []
    for image in images:
        fps = {f.kind: f for f in image.fingerprints}
        sha, ph = fps.get("sha256"), fps.get("phash")
        c = compare(
            sha_a=sha.value if sha else None, sha_b=prints.sha256,
            phash_a=ph.value if ph else None, phash_b=prints.phash,
            emb_a=None, emb_b=None, t=t,
        )
        if c.classification != "none":
            hits.append((image, c))
    return hits

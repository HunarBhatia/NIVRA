"""Comparing fingerprints and classifying matches (section 13.12).

A classification is a *suggestion for human review*, never a verdict that
an image is non-consensual. Thresholds come from settings, not code.
"""

import hashlib
import math
from dataclasses import dataclass
from typing import Literal

from app.fingerprint.phash import hamming

MatchClass = Literal["exact", "high", "possible", "none"]


@dataclass(frozen=True)
class Thresholds:
    phash_high: int = 6  # Hamming distance (of 64 bits) for a high-confidence match
    phash_possible: int = 12
    cosine_high: float = 0.95  # embedding agreement needed to lift a close pHash to "high"
    cosine_possible: float = 0.92  # embedding alone: at most a "possible" for review


@dataclass(frozen=True)
class Comparison:
    classification: MatchClass
    sha256_equal: bool
    phash_distance: int | None
    cosine: float | None


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("embeddings must have the same, non-zero length")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def compare(
    *,
    sha_a: str | None,
    sha_b: str | None,
    phash_a: str | None,
    phash_b: str | None,
    emb_a: list[float] | None,
    emb_b: list[float] | None,
    t: Thresholds,
) -> Comparison:
    sha_equal = bool(sha_a and sha_b and sha_a == sha_b)
    dist = hamming(phash_a, phash_b) if phash_a and phash_b else None
    cos = cosine(emb_a, emb_b) if emb_a and emb_b and len(emb_a) == len(emb_b) else None

    # The embedding (CLIP) measures what an image is ABOUT, not whether it is
    # the same picture: two different photos of a similar scene can score
    # 0.95+. So the embedding alone can never make a match "high"; it can
    # only raise a "possible" for human review, or confirm a pHash that
    # already looks close. (Found in testing: section 15.11.)
    phash_close = dist is not None and dist <= t.phash_possible
    if sha_equal:
        cls: MatchClass = "exact"
    elif (dist is not None and dist <= t.phash_high) or (
        phash_close and cos is not None and cos >= t.cosine_high
    ):
        cls = "high"
    elif (dist is not None and dist <= t.phash_possible) or (
        cos is not None and cos >= t.cosine_possible
    ):
        cls = "possible"
    else:
        cls = "none"
    return Comparison(cls, sha_equal, dist, None if cos is None else round(cos, 4))

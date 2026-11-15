"""pHash and comparison logic. Images here are synthetic, generated in memory."""

import json
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageEnhance

from app.fingerprint.compare import Thresholds, compare, cosine, sha256_hex
from app.fingerprint.phash import ALGORITHM, hamming, phash_from_gray, phash_image

FIXTURE = Path(__file__).parent / "fixtures" / "phash_vectors.json"
T = Thresholds()


def photo(seed: int, size=(640, 480)) -> Image.Image:
    """A photo-like test image: soft background plus random shapes."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size[1], 0:size[0]]
    base = np.stack([
        120 + 80 * np.sin(x / (40 + 10 * rng.random())),
        120 + 80 * np.cos(y / (50 + 10 * rng.random())),
        np.full(x.shape, 100 + 100 * rng.random()),
    ], axis=-1).clip(0, 255).astype("uint8")
    img = Image.fromarray(base, "RGB")
    draw = ImageDraw.Draw(img)
    for _ in range(12):
        x0, y0 = rng.integers(0, size[0] - 60), rng.integers(0, size[1] - 60)
        w, h = rng.integers(40, 200, 2)
        colour = tuple(int(c) for c in rng.integers(0, 256, 3))
        (draw.ellipse if rng.random() > 0.5 else draw.rectangle)(
            [x0, y0, x0 + w, y0 + h], fill=colour)
    return img


def encode(img: Image.Image, fmt="PNG", **kw) -> bytes:
    buf = BytesIO()
    img.save(buf, fmt, **kw)
    return buf.getvalue()


def test_shared_vectors_match_python():
    data = json.loads(FIXTURE.read_text())
    assert data["algorithm"] == ALGORITHM
    for v in data["vectors"]:
        assert phash_from_gray(np.array(v["gray"]).reshape(32, 32)) == v["phash"], v["name"]


def test_sha256_is_stable_and_exact():
    data = encode(photo(1))
    assert sha256_hex(data) == sha256_hex(data)
    assert sha256_hex(data) != sha256_hex(data + b"\0")


def test_phash_survives_resize_and_jpeg():
    original = photo(7)
    a = phash_image(encode(original))
    smaller = original.resize((320, 240), Image.Resampling.BILINEAR)
    b = phash_image(encode(smaller, "JPEG", quality=55))
    assert hamming(a, b) <= T.phash_high


def test_phash_survives_brightness_change():
    original = photo(8)
    brighter = ImageEnhance.Brightness(original).enhance(1.15)
    assert hamming(phash_image(encode(original)), phash_image(encode(brighter))) <= T.phash_high


def test_different_images_are_far_apart():
    distances = [hamming(phash_image(encode(photo(s))), phash_image(encode(photo(s + 100))))
                 for s in range(10, 16)]
    assert min(distances) > T.phash_possible, distances


def test_transparency_is_flattened_onto_white():
    rgba = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    white = Image.new("RGB", (64, 64), (255, 255, 255))
    assert phash_image(encode(rgba)) == phash_image(encode(white))


def test_hamming_counts_bits():
    assert hamming("0000000000000000", "ffffffffffffffff") == 64
    assert hamming("8000000000000000", "0000000000000001") == 2


def test_cosine():
    assert cosine([1, 0], [1, 0]) == pytest.approx(1)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0)
    with pytest.raises(ValueError):
        cosine([1], [1, 2])


@pytest.mark.parametrize("kwargs,expected", [
    (dict(sha_a="a" * 64, sha_b="a" * 64, phash_a="0" * 16, phash_b="f" * 16), "exact"),
    (dict(phash_a="0" * 16, phash_b="000000000000003f"), "high"),        # 6 bits
    (dict(phash_a="0" * 16, phash_b="0000000000000fff"), "possible"),    # 12 bits
    (dict(phash_a="0" * 16, phash_b="000000000001ffff"), "none"),        # 17 bits
    # Embedding alone (pHash far apart) is capped at "possible", however close.
    (dict(phash_a="0" * 16, phash_b="f" * 16, emb_a=[1, 0], emb_b=[1, 0.01]), "possible"),
    (dict(phash_a="0" * 16, phash_b="f" * 16, emb_a=[1, 0], emb_b=[1, 0.6]), "none"),
    # A borderline pHash (12 bits) plus strong embedding agreement -> "high".
    (dict(phash_a="0" * 16, phash_b="0000000000000fff", emb_a=[1, 0], emb_b=[1, 0.1]), "high"),
])
def test_classification(kwargs, expected):
    base = dict(sha_a=None, sha_b=None, phash_a=None, phash_b=None, emb_a=None, emb_b=None)
    assert compare(**{**base, **kwargs}, t=T).classification == expected

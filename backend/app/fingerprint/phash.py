"""Perceptual hash, algorithm "phash-dct-v1".

MUST stay identical to web/src/lib/fingerprint/phash.ts. Both are checked
against backend/tests/fixtures/phash_vectors.json.

Steps (the classic DCT pHash):
1. Fix orientation (EXIF), flatten transparency onto white.
2. Resize the colour image to 32x32.
3. Convert to grey with BT.601 luma: 0.299 R + 0.587 G + 0.114 B.
4. 2-D DCT-II of the 32x32 grey grid.
5. Keep the top-left 8x8 low-frequency block (64 values, DC included).
6. Bit = value > median + eps (eps = 1e-9 x largest |value|, so float noise
   can't flip bits), row-major, MSB first -> 16 hex chars.

Resized, recompressed or lightly edited copies keep most bits, so the
Hamming distance between hashes measures visual similarity.
"""

from io import BytesIO

import numpy as np
from PIL import Image, ImageOps

ALGORITHM = "phash-dct-v1"
SIZE = 32
LOW = 8

# DCT-II basis: C[k, n] = cos(pi * (2n + 1) * k / (2N)). Uniform scale factors
# are dropped because only comparisons against the median matter.
_n = np.arange(SIZE)
_DCT = np.cos(np.pi * (2 * _n[None, :] + 1) * _n[:, None] / (2 * SIZE))


def phash_from_gray(gray: np.ndarray) -> str:
    """gray: 32x32 array of luma values (any scale). Returns 16 hex chars."""
    if gray.shape != (SIZE, SIZE):
        raise ValueError("expected a 32x32 grey grid")
    g = gray.astype(np.float64)
    dct = _DCT @ g @ _DCT.T
    low = dct[:LOW, :LOW].flatten()
    median = np.median(low)
    # Coefficients that are mathematically equal to the median (common in
    # flat or symmetric images) differ only by floating-point noise, which
    # differs between NumPy and JavaScript. A tiny relative margin makes
    # those bits 0 on both sides.
    eps = 1e-9 * float(np.max(np.abs(low)))
    value = 0
    for bit in low > median + eps:
        value = (value << 1) | int(bit)
    return f"{value:016x}"


def gray32(image: Image.Image) -> np.ndarray:
    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        white = Image.new("RGBA", image.size, (255, 255, 255, 255))
        image = Image.alpha_composite(white, image)
    rgb = np.asarray(image.convert("RGB").resize((SIZE, SIZE), Image.Resampling.LANCZOS),
                     dtype=np.float64)
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def phash_image(data: bytes) -> str:
    with Image.open(BytesIO(data)) as img:
        return phash_from_gray(gray32(img))


def hamming(a: str, b: str) -> int:
    """Number of differing bits between two 64-bit hex hashes (0-64)."""
    return (int(a, 16) ^ int(b, 16)).bit_count()

"""Regenerates tests/fixtures/phash_vectors.json (shared Python/TypeScript pHash checks).

Run from backend/:  .venv/Scripts/python scripts/make_phash_vectors.py
Only regenerate if the algorithm version changes (then bump ALGORITHM).
"""

import json
from pathlib import Path

import numpy as np

from app.fingerprint.phash import ALGORITHM, phash_from_gray

rng = np.random.default_rng(20261114)
y, x = np.mgrid[0:32, 0:32]
grids = {
    "horizontal_gradient": x * 8,
    "vertical_gradient": y * 8,
    "checkerboard_4px": ((x // 4 + y // 4) % 2) * 255,
    "centre_blob": 255 * np.exp(-((x - 15.5) ** 2 + (y - 15.5) ** 2) / 60),
    "waves": 127 + 60 * np.sin(x / 3) + 60 * np.cos(y / 5),
    "noise_seeded": rng.integers(0, 256, (32, 32)),
}

vectors = []
for name, grid in grids.items():
    gray = np.clip(np.rint(grid), 0, 255).astype(int)
    vectors.append({"name": name, "gray": gray.flatten().tolist(), "phash": phash_from_gray(gray)})

out = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "phash_vectors.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"algorithm": ALGORITHM, "vectors": vectors}))
print(f"wrote {len(vectors)} vectors to {out}")
for v in vectors:
    print(v["name"], v["phash"])

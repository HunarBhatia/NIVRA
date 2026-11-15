"""Platform directory, loaded from the shared file (section 18.3).

Source of truth: ../shared/platforms.json (the website copies the same file).
Every entry is PROTOTYPE DATA with verified=false until a person checks it.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import get_settings


@lru_cache
def load() -> dict[str, Any]:
    path = Path(get_settings().platforms_file)
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data


def all_platforms() -> list[dict[str, Any]]:
    return load()["platforms"]


def get(platform_id: str | None) -> dict[str, Any] | None:
    return next((p for p in all_platforms() if p["id"] == platform_id), None)


def resolve(host: str) -> dict[str, Any] | None:
    """instagram.com, m.facebook.com, www.t.me ... -> platform entry (or None)."""
    host = host.lower().removeprefix("www.")
    for p in all_platforms():
        if any(host == d or host.endswith(f".{d}") for d in p["domains"]):
            return p
    return None

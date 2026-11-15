"""Scripted demo pages (PROJECT_DETAILS.txt section 24, decision D37).

For a demonstration, a REAL URL that blocks automated visits can be served
from a local copy instead: backend/demo_scripts/scripts.json lists the page
URLs and the local image files that stand in for the page's images. Only
the fetch is scripted - fingerprinting and comparison stay real, so only
the photo that is actually in the local copy matches.

- The folder is git-ignored: it may hold third-party photos.
- Only active when NIVRA_ENABLE_DEMO_SITES is on (never in production).
- Every scan entry from a scripted page is marked "scripted", the UI labels
  it "Scripted demo result", and real email delivery is refused for it.
"""

import html
import json
from pathlib import Path
from urllib.parse import urlsplit

from app.discovery.fetch import FetchError, FetchResult

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "demo_scripts"
IMAGE_PREFIX = "/__nivra_scripted__/"
_cache: dict = {"mtime": None, "pages": []}


def _norm(url: str) -> str:
    p = urlsplit(url.strip())
    host = (p.hostname or "").lower().removeprefix("www.")
    return f"{host}{p.path.rstrip('/')}"


def _pages() -> list[dict]:
    f = SCRIPTS_DIR / "scripts.json"
    if not f.is_file():
        return []
    mtime = f.stat().st_mtime
    if _cache["mtime"] != mtime:
        _cache["pages"] = json.loads(f.read_text(encoding="utf-8")).get("pages", [])
        _cache["mtime"] = mtime
    return _cache["pages"]


def _enabled() -> bool:
    from app.core.config import get_settings
    return get_settings().enable_demo_sites


def page_for(url: str) -> dict | None:
    if not _enabled():
        return None
    key = _norm(url)
    return next((p for p in _pages() if _norm(p["url"]) == key), None)


def is_scripted_url(url: str) -> bool:
    return page_for(url) is not None


def serve_scripted(url: str, max_bytes: int) -> FetchResult | None:
    """The local copy of a scripted page, or one of its images; None for
    anything else (the normal safe fetch then happens)."""
    if not _enabled():
        return None
    parts = urlsplit(url)
    if parts.path.startswith(IMAGE_PREFIX):
        host = (parts.hostname or "").lower().removeprefix("www.")
        name = parts.path[len(IMAGE_PREFIX):]
        for page in _pages():
            if _norm(page["url"]).split("/")[0] == host and name in page["images"]:
                body = (SCRIPTS_DIR / name).read_bytes()
                if len(body) > max_bytes:
                    raise FetchError("too_large", "That file is too large to check.")
                return FetchResult(url, 200, "image/jpeg", body)
        return None
    page = page_for(url)
    if page is None:
        return None
    origin = f"{parts.scheme}://{parts.netloc}"
    imgs = "".join(f'<img src="{origin}{IMAGE_PREFIX}{html.escape(n)}" alt="">' for n in page["images"])
    body = (f"<!doctype html><html><head><title>{html.escape(page.get('title', ''))}</title>"
            f"</head><body>{imgs}</body></html>").encode()
    return FetchResult(url, 200, "text/html", body)

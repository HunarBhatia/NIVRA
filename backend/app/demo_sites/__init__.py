"""Bundled demo websites (PROJECT_DETAILS.txt section 23, decision D34).

Real sites often refuse automated visits, which makes a live demonstration
unreliable. These five fake sites live under the reserved `.test` domain
(it can never be a real website) and are served from files in this folder
straight to the REAL scanner: the same fingerprinting, comparison, scan log,
AI drafting and sending run on them as on any real page.

Their copies are edits of web/public/demo/protected.jpg, a drawn scene with
no people. Enabled by NIVRA_ENABLE_DEMO_SITES (the API refuses to start with
it in production). Rebuild the files with the script described in the guide.
"""

from pathlib import Path
from urllib.parse import urlsplit

from app.discovery.fetch import FetchError, FetchResult

FILES = Path(__file__).parent / "files"

# host -> site. "pages" maps a URL path to a file in FILES.
DEMO_SITES: dict[str, dict] = {
    "snapgram.test": {
        "name": "Snapgram (demo)", "abuse": "abuse@snapgram.test",
        "about": "A photo post: the photo was cropped and colour-filtered.",
        "start": "/p/Cx8LqP2",
        "pages": {"/p/Cx8LqP2": "snapgram_post.html", "/media/snap_post.jpg": "snap_post.jpg",
                  "/media/avatar_a.jpg": "avatar_a.jpg", "/media/forest.jpg": "forest.jpg",
                  "/media/city.jpg": "city.jpg"},
    },
    "chatforum.test": {
        "name": "ChatForum (demo)", "abuse": "abuse@chatforum.test",
        "about": "A forum thread: a shrunk copy with a caption, among other pictures.",
        "start": "/thread/48213",
        "pages": {"/thread/48213": "forum_thread.html", "/img/avatar_a.jpg": "avatar_a.jpg",
                  "/img/avatar_b.jpg": "avatar_b.jpg", "/img/ocean.jpg": "ocean.jpg",
                  "/img/forum_upload.jpg": "forum_upload.jpg", "/img/city.jpg": "city.jpg"},
    },
    "imgdump.test": {
        "name": "ImgDump (demo)", "abuse": "abuse@imgdump.test",
        "about": "A direct image link: a byte-for-byte copy.",
        "start": "/i/9f3k2.jpg",
        "pages": {"/i/9f3k2.jpg": "dump_exact.jpg"},
    },
    "travelblog.test": {
        "name": "Travel Blog (demo)", "abuse": "abuse@travelblog.test",
        "about": "A blog with a different lake photo: similar subject, not your photo.",
        "start": "/2026/lakes-of-the-north",
        "pages": {"/2026/lakes-of-the-north": "blog_post.html", "/photos/blog_lake.jpg": "blog_lake.jpg",
                  "/photos/forest.jpg": "forest.jpg", "/photos/ocean.jpg": "ocean.jpg"},
    },
    "privategroup.test": {
        "name": "PrivateGroup (demo)", "abuse": "abuse@privategroup.test",
        "about": "A members-only group: it blocks automated visits, like many real sites.",
        "start": "/g/hidden-album",
        "blocked": True, "pages": {},
    },
}

TYPES = {".html": "text/html", ".jpg": "image/jpeg", ".png": "image/png"}


def demo_links() -> list[dict]:
    return [{"url": f"https://{host}{s['start']}", "site": s["name"], "about": s["about"]}
            for host, s in DEMO_SITES.items()]


def serve_demo(url: str, max_bytes: int) -> FetchResult | None:
    """Returns the bundled response for a demo URL, or None if the URL is not
    one of the demo sites (then the normal, safe network fetch happens)."""
    parts = urlsplit(url)
    site = DEMO_SITES.get((parts.hostname or "").lower())
    if site is None or parts.scheme not in ("http", "https"):
        return None
    if site.get("blocked"):
        raise FetchError("forbidden", "That page needs a login or blocks automated visits, so "
                                      "Nivra can't check it. You can still report the link.")
    name = site["pages"].get(parts.path.rstrip("/") or "/")
    if name is None:
        raise FetchError("not_found", "That page doesn't exist (it may already be removed).")
    body = (FILES / name).read_bytes()
    if len(body) > max_bytes:
        raise FetchError("too_large", "That file is too large to check.")
    return FetchResult(url, 200, TYPES[Path(name).suffix], body)

"""Extracts candidate image URLs from an HTML page (stdlib parser only)."""

from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

MAX_CANDIDATES = 25


class _ImageCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: list[str] = []
        self.imgs: list[str] = []
        self.title: str | None = None
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key in ("og:image", "og:image:url", "og:image:secure_url", "twitter:image"):
                self.meta.append(a.get("content", ""))
        elif tag == "img":
            # Prefer the largest srcset entry; fall back to src / lazy-load attributes.
            srcset = a.get("srcset") or a.get("data-srcset")
            if srcset:
                best = _largest_from_srcset(srcset)
                if best:
                    self.imgs.append(best)
            for attr in ("src", "data-src", "data-original"):
                if a.get(attr):
                    self.imgs.append(a[attr])
                    break
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title and self.title is None and data.strip():
            self.title = data.strip()[:200]


def _largest_from_srcset(srcset: str) -> str | None:
    best, best_w = None, -1.0
    for part in srcset.split(","):
        bits = part.strip().split()
        if not bits:
            continue
        w = 0.0
        if len(bits) > 1 and bits[1][:-1].replace(".", "", 1).isdigit():
            w = float(bits[1][:-1])
        if w > best_w:
            best, best_w = bits[0], w
    return best


def extract_image_urls(html: str, base_url: str) -> tuple[list[str], str | None]:
    """Returns (absolute image URLs, page title). Social-preview images first,
    data: URIs and non-http links dropped, duplicates removed, capped."""
    p = _ImageCollector()
    try:
        p.feed(html)
    except Exception:  # malformed HTML: keep whatever was collected
        pass
    seen: set[str] = set()
    out: list[str] = []
    for raw in p.meta + p.imgs:
        raw = raw.strip()
        if not raw or raw.startswith("data:"):
            continue
        absolute = urljoin(base_url, raw)
        if urlsplit(absolute).scheme not in ("http", "https") or absolute in seen:
            continue
        seen.add(absolute)
        out.append(absolute)
        if len(out) >= MAX_CANDIDATES:
            break
    return out, p.title

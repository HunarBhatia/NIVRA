"""Link validation and the link status state machine (blueprint 10.5).

The frontend shows only the buttons that make sense, but the server is the
one that enforces which status changes are allowed.
"""

from urllib.parse import urlsplit

MAX_URL_LENGTH = 2048

# status -> statuses it may move to
TRANSITIONS: dict[str, set[str]] = {
    "found": {"reported"},
    "reported": {"removed", "rejected", "escalated"},
    "rejected": {"escalated", "reported"},
    "escalated": {"removed", "rejected"},
    "removed": {"reappeared"},
    "reappeared": {"reported"},
}


class InvalidUrl(ValueError):
    pass


def normalise_url(raw: str) -> tuple[str, str]:
    """Returns (url, host). Accepts 'instagram.com/p/x' and adds https://.

    Only http(s) links to real-looking hostnames are accepted; anything else
    (javascript:, file:, bare words, IP-less junk) is rejected.
    """
    text = raw.strip()
    if not text or len(text) > MAX_URL_LENGTH or any(c.isspace() for c in text):
        raise InvalidUrl("not a link")
    if "://" not in text:
        text = f"https://{text}"
    parts = urlsplit(text)
    if parts.scheme.lower() not in {"http", "https"}:
        raise InvalidUrl("only http and https links are allowed")
    host = (parts.hostname or "").lower()
    if "." not in host or host.startswith(".") or host.endswith("."):
        raise InvalidUrl("not a link")
    if parts.username or parts.password:
        raise InvalidUrl("links with embedded credentials are not allowed")
    return text, host.removeprefix("www.")


def can_transition(current: str, new: str) -> bool:
    return new in TRANSITIONS.get(current, set())

"""Sending approved takedown notices by email (section 22.6, decision D30).

After ONE approval by the user, Nivra emails the notice itself to every
channel that accepts email:
- addresses listed for the platform in shared/platforms.json, or
- for sites not in the directory: the abuse contact of the company hosting
  the site, found automatically through RDAP (the public registry lookup
  that replaced WHOIS for IP addresses).

Platforms that only accept their own web form (Instagram, TikTok, X ...)
can't be emailed - Nivra says so and the UI opens the form with the notice
copied. Nothing is sent without the user's approval.
"""

import ipaddress
import logging
import socket
import time
from typing import Any

import httpx

from app import platforms
from app.discovery.fetch import is_public_ip

log = logging.getLogger("nivra.sending")
RDAP_URL = "https://rdap.org/ip/{ip}"
_cache: dict[str, tuple[float, str | None]] = {}
CACHE_SECONDS = 3600


def _emails_with_role(entity: dict[str, Any], role: str) -> list[str]:
    """Walks an RDAP entity tree and returns emails of entities with `role`."""
    found = []
    if role in (entity.get("roles") or []):
        vcard = entity.get("vcardArray") or []
        for item in (vcard[1] if len(vcard) > 1 else []):
            if isinstance(item, list) and len(item) >= 4 and item[0] == "email":
                found.append(str(item[3]).strip().lower())
    for child in entity.get("entities") or []:
        found.extend(_emails_with_role(child, role))
    return found


def fetch_rdap(ip: str) -> dict[str, Any]:
    """Public registry lookup (rdap.org redirects to the right regional
    registry). Only rdap.org and the registries are contacted - never the
    site itself."""
    with httpx.Client(timeout=10, follow_redirects=True,
                      headers={"Accept": "application/rdap+json"}) as client:
        r = client.get(RDAP_URL.format(ip=ip))
        r.raise_for_status()
        return r.json()


def host_abuse_email(host: str, lookup=None) -> str | None:
    """Abuse contact for whoever hosts `host` (or None if not found)."""
    now = time.time()
    cached = _cache.get(host)
    if cached and now - cached[0] < CACHE_SECONDS:
        return cached[1]
    email = None
    try:
        ip = socket.gethostbyname(host)
        if is_public_ip(ip) and ipaddress.ip_address(ip):
            data = (lookup or fetch_rdap)(ip)
            emails = _emails_with_role(data, "abuse")
            email = emails[0] if emails else None
    except (OSError, httpx.HTTPError, ValueError, KeyError) as e:
        log.info("Abuse lookup failed: %s", type(e).__name__)
    _cache[host] = (now, email)
    return email


def recipients_for(host: str, lookup=None) -> dict[str, Any]:
    """Where a notice for a link on `host` can be emailed.

    Returns {"emails": [{"address", "why"}], "form_only": bool,
             "forms": [{"label", "target"}]}.
    """
    p = platforms.resolve(host)
    if p is not None:
        emails = [{"address": m["target"], "why": m["label"]}
                  for m in p["mechanisms"] if m["kind"] == "email" and m.get("target")]
        forms = [{"label": m["label"], "target": m.get("target")}
                 for m in p["mechanisms"] if m["kind"] in ("form", "in-app")]
        return {"emails": emails, "form_only": not emails, "forms": forms, "platform": p["name"]}
    abuse = host_abuse_email(host, lookup)
    return {"emails": [{"address": abuse, "why": f"Abuse contact of the company hosting {host}"}]
            if abuse else [], "form_only": False, "forms": [], "platform": None}

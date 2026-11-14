"""The only code allowed to make outgoing web requests.

Safety rules (PROJECT_DETAILS.txt 16.4-16.7):
- SSRF: hostnames are resolved first and every address must be public;
  the request is then sent to that exact IP (TLS still verifies the real
  hostname), so DNS can't be switched to an internal address mid-request.
- Redirects are followed manually (max 3) and every hop is re-checked.
- Only http/https on ports 80/443. Strict timeouts and size caps.
- robots.txt is honoured for our user agent; 401/403/429 are respected,
  never worked around (no logins, no CAPTCHA solving).
- Nothing here logs URLs or content.
"""

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.core.config import get_settings

USER_AGENT = "NivraBot/0.1 (image takedown assistant; respects robots.txt)"
MAX_REDIRECTS = 3


class FetchError(Exception):
    """A safe, user-facing reason a fetch didn't happen. `code` is stored."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class FetchResult:
    url: str  # final URL after redirects
    status: int
    content_type: str
    body: bytes


Resolver = Callable[[str], list[str]]


def _system_resolver(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise FetchError("dns", "That website's address couldn't be found.") from None
    return sorted({info[4][0] for info in infos})


def is_public_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


@dataclass
class SafeFetcher:
    resolver: Resolver = _system_resolver
    allow_private: bool = field(default_factory=lambda: get_settings().discovery_allow_private_hosts)
    timeout: float = 10.0
    transport: httpx.BaseTransport | None = None  # tests inject a mock transport
    _robots: dict[str, RobotFileParser | None] = field(default_factory=dict)

    # ---------- URL + address checks ----------

    def _check_url(self, url: str) -> tuple[str, str, int]:
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        if scheme not in ("http", "https"):
            raise FetchError("scheme", "Only http and https links can be checked.")
        host = (parts.hostname or "").lower()
        if not host:
            raise FetchError("url", "That doesn't look like a web address.")
        port = parts.port or (443 if scheme == "https" else 80)
        if port not in (80, 443) and not self.allow_private:
            raise FetchError("port", "Only standard web ports can be checked.")
        return scheme, host, port

    def _pick_ip(self, host: str) -> str:
        try:
            ips = [str(ipaddress.ip_address(host))]  # host is already an IP
        except ValueError:
            ips = self.resolver(host)
        if not ips:
            raise FetchError("dns", "That website's address couldn't be found.")
        if not self.allow_private and not all(is_public_ip(ip) for ip in ips):
            # Any private address is refused, even if public ones exist too.
            raise FetchError("private", "That address points to a private network, so it can't be checked.")
        return ips[0]

    # ---------- one request to a pinned IP ----------

    def _request(self, url: str, max_bytes: int) -> httpx.Response | FetchResult:
        scheme, host, port = self._check_url(url)
        ip = self._pick_ip(host)
        parts = urlsplit(url)
        ip_host = f"[{ip}]" if ":" in ip else ip
        netloc = ip_host if port in (80, 443) else f"{ip_host}:{port}"
        pinned = urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))
        headers = {
            "Host": host if port in (80, 443) else f"{host}:{port}",
            "User-Agent": USER_AGENT,
            "Accept": "text/html,image/*;q=0.9,*/*;q=0.5",
        }
        ext = {"sni_hostname": host} if scheme == "https" else {}
        with httpx.Client(timeout=self.timeout, follow_redirects=False,
                          transport=self.transport) as client:
            with client.stream("GET", pinned, headers=headers, extensions=ext) as resp:
                if resp.is_redirect:
                    return resp
                declared = resp.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    raise FetchError("too_large", "That file is too large to check.")
                body = bytearray()
                for chunk in resp.iter_bytes():
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        raise FetchError("too_large", "That file is too large to check.")
                return FetchResult(url, resp.status_code,
                                   resp.headers.get("content-type", "").split(";")[0].strip().lower(),
                                   bytes(body))

    def get(self, url: str, max_bytes: int, check_robots: bool = True) -> FetchResult:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            # Scheme, port and address first, so the user sees the real reason
            # (the request itself re-checks the address before connecting).
            _, host, _ = self._check_url(current)
            self._pick_ip(host)
            if check_robots and not self.allowed_by_robots(current):
                raise FetchError("robots", "That website asks automated tools not to visit this page.")
            try:
                result = self._request(current, max_bytes)
            except httpx.TimeoutException:
                raise FetchError("timeout", "That website took too long to respond.") from None
            except httpx.HTTPError:
                raise FetchError("network", "We couldn't connect to that website.") from None
            if isinstance(result, httpx.Response):  # redirect
                location = result.headers.get("location")
                if not location:
                    raise FetchError("redirect", "That website sent a broken redirect.")
                current = str(httpx.URL(current).join(location))
                continue
            if result.status in (401, 403):
                raise FetchError("forbidden", "That page needs a login or blocks automated visits, so "
                                              "Nivra can't check it. You can still report the link.")
            if result.status == 429:
                raise FetchError("rate_limited", "That website asked us to slow down. Try again later.")
            if result.status == 404:
                raise FetchError("not_found", "That page doesn't exist (it may already be removed).")
            if result.status >= 500:
                raise FetchError("server_error", "That website is having problems. Try again later.")
            if result.status >= 400:
                raise FetchError("client_error", "That website refused the request.")
            return result
        raise FetchError("redirect", "That link redirects too many times.")

    # ---------- robots.txt ----------

    def allowed_by_robots(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser: RobotFileParser | None = RobotFileParser()
            try:
                res = self.get(f"{origin}/robots.txt", max_bytes=500_000, check_robots=False)
                parser.parse(res.body.decode("utf-8", "replace").splitlines())
            except FetchError as e:
                # Standard behaviour: no robots.txt (4xx) = allowed; a server
                # error or failure to connect = be cautious and don't crawl.
                parser = None if e.code in ("not_found", "forbidden", "client_error") else _deny_all()
            self._robots[origin] = parser
        parser = self._robots[origin]
        return True if parser is None else parser.can_fetch(USER_AGENT, url)


def _deny_all() -> RobotFileParser:
    p = RobotFileParser()
    p.parse(["User-agent: *", "Disallow: /"])
    return p

"""Discovery providers: pluggable sources of candidate images.

Every provider implements DiscoveryProvider. New sources (a licensed
search API, a platform integration, scheduled re-checks) are added as new
classes and registered in PROVIDERS - the job runner doesn't change.

Rule from D13: a provider must work from fingerprints and URLs. A provider
that needs the ORIGINAL image (e.g. a reverse-image-search API) would break
D13 and is not allowed without a separate, explicit user decision (16.12).
"""

import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass

from app.core.config import get_settings
from app.discovery.fetch import FetchError, SafeFetcher
from app.discovery.parse import extract_image_urls

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp"}


@dataclass
class Candidate:
    """A possible copy. `data` lives only in memory for the matching step."""

    image_url: str
    source_page_url: str
    data: bytes


@dataclass
class DiscoveryReport:
    page_title: str | None = None
    found: int = 0  # image URLs found on the page
    skipped: int = 0  # couldn't be fetched/decoded or blocked by robots.txt


class DiscoveryProvider(ABC):
    name: str
    needs_original_image: bool = False

    @abstractmethod
    def discover(self, url: str, fetcher: SafeFetcher, report: DiscoveryReport) -> Iterator[Candidate]:
        """Yields candidates. Raises FetchError if the whole input can't be read."""


class UserSubmittedUrlProvider(DiscoveryProvider):
    """Checks a page (or a direct image link) that the user gave us.

    The user directs us to one specific URL, like opening it themselves;
    robots.txt, rate limits and access controls are still respected.
    """

    name = "user_url"

    def __init__(self, delay_seconds: float = 0.5):
        self.delay = delay_seconds  # politeness pause between requests to a site
        s = get_settings()
        self.max_page = s.discovery_max_page_bytes
        self.max_image = s.discovery_max_image_bytes

    def discover(self, url: str, fetcher: SafeFetcher, report: DiscoveryReport) -> Iterator[Candidate]:
        first = fetcher.get(url, max_bytes=max(self.max_page, self.max_image))
        if first.content_type in IMAGE_TYPES:
            report.found = 1
            yield Candidate(first.url, first.url, first.body)
            return
        if first.content_type not in ("text/html", "application/xhtml+xml"):
            raise FetchError("not_html", "That link isn't a web page or an image Nivra can read.")
        if len(first.body) > self.max_page:
            raise FetchError("too_large", "That page is too large to check.")

        image_urls, title = extract_image_urls(first.body.decode("utf-8", "replace"), first.url)
        report.page_title = title
        report.found = len(image_urls)
        for image_url in image_urls:
            time.sleep(self.delay)
            try:
                res = fetcher.get(image_url, max_bytes=self.max_image)
            except FetchError:
                report.skipped += 1
                continue
            if res.content_type not in IMAGE_TYPES:  # e.g. SVG, HTML error pages
                report.skipped += 1
                continue
            yield Candidate(res.url, first.url, res.body)


PROVIDERS: dict[str, DiscoveryProvider] = {
    UserSubmittedUrlProvider.name: UserSubmittedUrlProvider(),
}

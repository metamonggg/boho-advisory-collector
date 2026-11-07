from __future__ import annotations

import time
from typing import Protocol
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from boho_rss.settings import Settings


class HttpClient(Protocol):
    def get(self, url: str) -> requests.Response: ...


def normalize_detail_url(url: str) -> str:
    parts = urlsplit(url)
    query = parse_qs(parts.query, keep_blank_values=True)
    if (
        parts.hostname == "www.boho.or.kr"
        and parts.path == "/kr/bbs/view.do"
        and query.get("bbsId") == ["B0000133"]
        and "nttId" in query
        and "menuNo" not in query
    ):
        query["menuNo"] = ["205020"]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, doseq=True), parts.fragment))


class BohoHttpClient:
    def __init__(self, settings: Settings) -> None:
        self.timeout = settings.request_timeout_seconds
        self.interval = settings.request_interval_seconds
        self._last_request_at = 0.0
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": settings.user_agent})
        retry = Retry(
            total=settings.request_retries,
            connect=settings.request_retries,
            read=settings.request_retries,
            status=settings.request_retries,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def get(self, url: str) -> requests.Response:
        elapsed = time.monotonic() - self._last_request_at
        if self._last_request_at and elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        response = self.session.get(normalize_detail_url(url), timeout=self.timeout)
        self._last_request_at = time.monotonic()
        response.raise_for_status()
        return response

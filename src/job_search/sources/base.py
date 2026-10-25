"""Shared HTTP client, HTML-to-text conversion and per-source error isolation."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from html.parser import HTMLParser

import httpx

from job_search.models import Posting

USER_AGENT = "job-search/0.1 (personal daily job digest)"
_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section"}


def make_client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True)


def get_with_retry(client: httpx.Client, url: str, retries: int = 2, **kwargs) -> httpx.Response:
    """GET that retries on 429/5xx and on dropped connections, with a short backoff."""
    for attempt in range(retries + 1):
        try:
            resp = client.get(url, **kwargs)
        except httpx.TransportError:
            if attempt == retries:
                raise
            time.sleep(2 * (attempt + 1))
            continue
        if resp.status_code not in (429, 500, 502, 503, 504) or attempt == retries:
            resp.raise_for_status()
            return resp
        time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("- ")

    def handle_endtag(self, tag):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def html_to_text(raw: str | None) -> str:
    """Plain text with one line per block element.

    Some feeds entity-escape their HTML, fully or mixed with real tags, so a second pass runs when
    the first one still leaves markup behind.
    """
    if not raw:
        return ""
    text = _extract(raw)
    if _LEFTOVER_TAG.search(text):
        text = _extract(text)
    return text


_LEFTOVER_TAG = re.compile(r"</?(p|div|br|li|ul|ol|strong|em|span|h[1-6])\b[^>]*>", re.IGNORECASE)


def _extract(raw: str) -> str:
    parser = _TextExtractor()
    parser.feed(raw)
    text = "".join(parser.parts).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def parse_date(value) -> date | None:
    """ISO strings, RFC-822 strings, or epoch seconds/milliseconds -> date."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            seconds = value / 1000 if value > 1e11 else value
            return datetime.fromtimestamp(seconds, tz=timezone.utc).date()
        text = str(value)
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(text).date()
    except (ValueError, TypeError, OverflowError):
        return None


@dataclass
class SourceResult:
    name: str
    postings: list[Posting] = field(default_factory=list)
    error: str | None = None


def run_source(name: str, fetch: Callable[[], list[Posting]]) -> SourceResult:
    """Run one source; an exception is recorded, never propagated (one bad source can't stop the run)."""
    try:
        return SourceResult(name, fetch())
    except Exception as exc:  # noqa: BLE001 - isolation is the point
        return SourceResult(name, error=f"{type(exc).__name__}: {exc}"[:300])

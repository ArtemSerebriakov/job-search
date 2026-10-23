"""Rule: the posting must have a direct link to the job ad itself."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

from job_search.models import Posting, Verdict

RULE = "link"

_SEARCH_HOSTS = re.compile(r"(^|\.)(google|bing|duckduckgo|yahoo|yandex)\.[a-z.]+$")
_SEARCH_QUERY_KEYS = {"q", "query", "keywords", "keyword", "search", "searchterm", "k", "what", "kw"}
_LISTING_PATHS = re.compile(
    r"^/(?:[a-z]{2}(?:-[a-z]{2})?/)?(?:(?:careers?|karriere|about|company)/)?(jobs|careers|career|karriere|vacancies|vacatures|stellenangebote|"
    r"positions|openings|join-us|jobs/search|search|jobs/search-results|open-positions)/?$",
    re.IGNORECASE,
)
_ARTICLE_PATHS = re.compile(r"/(news|blog|press|article|articles|magazine|stories)/", re.IGNORECASE)


def check(posting: Posting) -> Verdict:
    url = posting.url.strip()
    if not url:
        return Verdict.fail(RULE, "no URL")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return Verdict.fail(RULE, "not an http(s) URL", url)
    host = parts.netloc.lower().removeprefix("www.")
    if _SEARCH_HOSTS.search(host):
        return Verdict.fail(RULE, "search-engine URL, not a posting", url)
    if host.endswith("linkedin.com") and "/jobs/view/" not in parts.path:
        return Verdict.fail(RULE, "LinkedIn search/listing URL, not a posting", url)
    query_keys = {k.lower() for k in parse_qs(parts.query)}
    if query_keys & _SEARCH_QUERY_KEYS and not _has_job_id(parts.path, parts.query):
        return Verdict.fail(RULE, "search-results URL, not a posting", url)
    if _LISTING_PATHS.match(parts.path) and not _has_job_id(parts.path, parts.query):
        return Verdict.fail(RULE, "careers listing page, not a posting", url)
    if _ARTICLE_PATHS.search(parts.path):
        return Verdict.fail(RULE, "article/blog URL, not a posting", url)
    return Verdict.ok(RULE)


def _has_job_id(path: str, query: str) -> bool:
    """Heuristic: a posting URL carries an id (digits, uuid, or gh_jid/jobId param)."""
    if re.search(r"(gh_jid|jobid|job_id|jid|vacancyid|id)=\w+", query, re.IGNORECASE):
        return True
    return bool(re.search(r"\d{4,}|[0-9a-f]{8}-[0-9a-f]{4}-", path, re.IGNORECASE))

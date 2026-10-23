"""URL normalisation, report-history parsing and repost fingerprinting."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from job_search.config import normalize_company
from job_search.models import Posting, Verdict

RULE = "dedup"
REPORT_GLOB = "job-search_daily-reports_*.md"

_TRACKING_PARAMS = {
    "gh_src", "gh_jid_src", "source", "src", "ref", "referrer", "trk", "trackingid",
    "gclid", "fbclid", "mc_cid", "mc_eid", "lever-source", "lever-origin", "lever-via",
    "utm", "from", "campaign", "rx_source", "rx_campaign", "rx_medium",
}
_URL_RE = re.compile(r"https?://[^\s<>()\[\]\"'`|]+")
_GENDER_TAG = re.compile(
    r"\((?:[mwfdxai]\s*/\s*){1,3}[mwfdxai]\)|\((?:all genders?|alle geschlechter)\)|\bm/w/d\b|\bf/m/x\b|\bm/f/d\b|\bw/m/d\b",
    re.IGNORECASE,
)


def normalize_url(url: str) -> str:
    """Canonical form used for dedup: lowercase host, no www, no fragment,
    no tracking params, sorted query, no trailing slash."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_PARAMS
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, urlencode(query), ""))


def normalize_title(title: str) -> str:
    s = _GENDER_TAG.sub(" ", title.lower())
    s = re.sub(r"[^\w+#]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def fingerprint(company: str, title: str) -> str:
    """Identity of a role independent of its URL, used to detect reposts."""
    return f"{normalize_company(company)}|{normalize_title(title)}"


def urls_in_reports(reports_dir: Path, before: date | None = None) -> set[str]:
    """Normalised URLs of every posting in daily report files dated before `before` (all if None).

    Re-running a day must not treat that day's own report as history.
    """
    urls: set[str] = set()
    for path in sorted(reports_dir.glob(REPORT_GLOB)):
        day = path.stem.removeprefix(REPORT_GLOB.split("*")[0])
        if before is not None and day >= before.isoformat():
            continue
        for match in _URL_RE.findall(path.read_text()):
            urls.add(normalize_url(match.rstrip(".,;:")))
    return urls


def check_duplicate(
    posting: Posting,
    reported_urls: set[str],
    reported_fingerprints: dict[str, bool],
) -> Verdict:
    """Fail if the posting was already reported, by URL or as a repost.

    `reported_fingerprints` maps fingerprint -> True if the earlier posting is known to have
    closed since. A repost of a closed role counts as reopened and is allowed (flagged).
    """
    norm = normalize_url(posting.url)
    if norm in reported_urls:
        return Verdict.fail(RULE, "URL already reported on an earlier day", norm)
    fp = fingerprint(posting.company, posting.title)
    if fp in reported_fingerprints:
        if reported_fingerprints[fp]:
            return Verdict.flag(RULE, "reopened: same role was reported before and later closed", fp)
        return Verdict.fail(RULE, "repost of a role already reported (new URL, same company and title)", fp)
    return Verdict.ok(RULE)


def collapse_duplicates(postings: list[Posting]) -> tuple[list[Posting], list[Posting]]:
    """Keep one posting per (company, normalised title) within a run — the same role listed for
    several locations or by several sources. Prefers the employer's own listing, then more text.
    Returns (kept, dropped); kept keeps the order of first appearance."""
    best: dict[str, Posting] = {}
    order: list[str] = []
    for p in postings:
        fp = fingerprint(p.company, p.title)
        if fp not in best:
            order.append(fp)
            best[fp] = p
        elif (p.source_is_origin, len(p.description)) > (best[fp].source_is_origin, len(best[fp].description)):
            best[fp] = p
    kept = [best[fp] for fp in order]
    kept_ids = {id(p) for p in kept}
    return kept, [p for p in postings if id(p) not in kept_ids]

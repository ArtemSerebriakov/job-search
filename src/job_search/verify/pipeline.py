"""Runs every hard rule on a posting. Any FAIL excludes it; FLAGs travel to the report."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from job_search.config import Criteria
from job_search.dedup import check_duplicate
from job_search.models import Posting, Verdict, VerificationResult
from job_search.verify import description_language, enrollment, language, link, liveness, location, seniority


def static_checks(posting: Posting, criteria: Criteria) -> list[Callable[[], Verdict]]:
    """Rules that need no network, cheapest first."""
    return [
        lambda: link.check(posting),
        lambda: location.check(posting, criteria),
        lambda: enrollment.check(posting),
        lambda: seniority.check(posting, criteria.max_min_years),
        lambda: description_language.check(posting),
        lambda: language.check(posting),
    ]


def verify(
    posting: Posting,
    criteria: Criteria,
    reported_urls: set[str],
    reported_fingerprints: dict[str, bool],
    client: httpx.Client | None = None,
) -> VerificationResult:
    """Dedup + static rules, stopping at the first FAIL; liveness last and only if `client` is given."""
    verdicts = [check_duplicate(posting, reported_urls, reported_fingerprints)]
    if verdicts[0].status != "fail":
        for rule in static_checks(posting, criteria):
            verdict = rule()
            verdicts.append(verdict)
            if verdict.status == "fail":
                break
    if client is not None and all(v.status != "fail" for v in verdicts):
        verdicts.append(liveness.check(posting, client))
    return VerificationResult(posting_id=posting.id, verdicts=verdicts)

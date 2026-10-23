"""JobsPipe search API (https://api.jobspipe.dev): an aggregator of 30+ boards, public employment
services (EURES) and company hiring platforms.

Every returned job costs one credit (a job already paid for is free when it returns), so filters are
applied on JobsPipe's side and each run stops at `max_results` jobs.
"""

from __future__ import annotations

import os
import time

import httpx

from job_search.models import Posting
from job_search.sources.base import parse_date
from job_search.sources.relevance import is_relevant_title

API = "https://api.jobspipe.dev/v1/jobs/search"
# Company hiring platforms: a job seen there is the employer's own listing.
ATS_SOURCES = {"greenhouse", "workday", "ashby", "lever", "workable", "recruitee", "personio", "smartrecruiters",
               "breezy", "paylocity", "manatal", "jobscore", "teamtailor", "pinpoint", "hirehive"}


class MissingKey(RuntimeError):
    pass


def search(client: httpx.Client, filters: dict, max_results: int, page_size: int = 25) -> list[dict]:
    """Run one search, following cursors until `max_results` jobs (credits) are used."""
    key = os.environ.get("JOBSPIPE_API_KEY")
    if not key:
        raise MissingKey("JOBSPIPE_API_KEY not set (add it to .env)")
    jobs: list[dict] = []
    cursor = None
    while len(jobs) < max_results:
        body = {**filters, "limit": min(page_size, max_results - len(jobs))}
        if cursor:
            body["cursor"] = cursor
        for attempt in range(3):
            resp = client.post(API, json=body, headers={"Authorization": f"Bearer {key}"})
            if resp.status_code != 429 or attempt == 2:
                break
            time.sleep(1 + attempt)
        resp.raise_for_status()
        payload = resp.json()
        jobs.extend(payload.get("data") or [])
        cursor = (payload.get("metadata") or {}).get("next_cursor")
        if not cursor:
            break
        time.sleep(0.6)  # free plan: 2 requests per second
    return jobs


def _source_name(entry) -> str | None:
    """`sources[]` entries look like {"provider": "indeed", "url": ..., "seen_at": ...}."""
    if isinstance(entry, dict):
        return entry.get("provider") or entry.get("source")
    return str(entry) if entry else None


def to_posting(job: dict, company_override: str | None = None) -> Posting | None:
    if job.get("status") == "closed" or not job.get("url"):
        return None
    sources = {name.lower() for name in map(_source_name, job.get("sources") or []) if name}
    url = job["url"]
    return Posting(
        source="jobspipe:" + ",".join(sorted(sources) or ["unknown"]),
        url=url, title=job.get("job_title") or "", company=company_override or job.get("company") or "",
        location=job.get("long_location") or job.get("location") or "",
        country=job.get("country_code"), city=(job.get("cities") or [None])[0],
        remote=bool(job.get("remote")), remote_regions=job.get("country_codes") or [],
        description=job.get("description") or "", posted_at=parse_date(job.get("date_posted")),
        source_is_origin=bool(sources & ATS_SOURCES),
    )


def fetch(client: httpx.Client, searches: list[dict], max_results_per_day: int) -> list[Posting]:
    """Run the configured searches in order until the daily credit budget is spent."""
    budget = max_results_per_day
    seen: dict[str, Posting] = {}
    for spec in searches:
        if budget <= 0:
            break
        limit = min(spec.get("max_results", budget), budget)
        jobs = search(client, spec["filters"], limit)
        budget -= len(jobs)
        for job in jobs:
            posting = to_posting(job)
            if posting and is_relevant_title(posting.title) and job.get("id") not in seen:
                seen[str(job.get("id"))] = posting
    return list(seen.values())

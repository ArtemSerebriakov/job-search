"""Job-board APIs: Bundesagentur für Arbeit, Arbeitnow, Himalayas, RemoteOK.

These are aggregators, not the employer's own page (source_is_origin=False), so the liveness rule
flags their postings as "only verified on an aggregator" unless a better source is found.
"""

from __future__ import annotations

import base64

import httpx

from job_search.models import Posting
from job_search.sources.base import get_with_retry, html_to_text, parse_date
from job_search.sources.relevance import is_relevant_title

_BA = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
_BA_HEADERS = {"X-API-Key": "jobboerse-jobsuche"}  # public client id used by the official web app
# Seniority values on Himalayas that can never be early-career.
_HIMALAYAS_TOO_SENIOR = {"Mid-level", "Senior", "Manager", "Director", "Executive", "Lead"}


def arbeitsagentur(client: httpx.Client, queries: list[str], published_within_days: int, max_pages: int) -> list[Posting]:
    listings: dict[str, dict] = {}
    for query in queries:
        for page in range(1, max_pages + 1):
            data = get_with_retry(client, f"{_BA}/pc/v6/jobs", headers=_BA_HEADERS, params={
                "was": query, "angebotsart": 1, "veroeffentlichtseit": published_within_days,
                "size": 100, "page": page,
            }).json()
            results = data.get("ergebnisliste") or []
            for job in results:
                if is_relevant_title(job.get("stellenangebotsTitel", "")):
                    listings.setdefault(job["referenznummer"], job)
            if len(results) < 100:
                break

    postings = []
    for ref, job in listings.items():
        encoded = base64.b64encode(ref.encode()).decode()
        detail = get_with_retry(client, f"{_BA}/pc/v4/jobdetails/{encoded}", headers=_BA_HEADERS).json()
        address = ((job.get("stellenlokationen") or [{}])[0].get("adresse") or {})
        postings.append(Posting(
            source="arbeitsagentur", url=f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{ref}",
            title=job["stellenangebotsTitel"], company=job.get("firma", ""),
            location=", ".join(x for x in (address.get("ort"), "Germany") if x), country="DE",
            city=address.get("ort"), description=detail.get("stellenangebotsBeschreibung", ""),
            posted_at=parse_date(job.get("datumErsteVeroeffentlichung")),
        ))
    return postings


def arbeitnow(client: httpx.Client, max_pages: int) -> list[Posting]:
    postings = []
    for page in range(1, max_pages + 1):
        data = get_with_retry(client, "https://www.arbeitnow.com/api/job-board-api", params={"page": page}).json()
        for job in data.get("data", []):
            if not is_relevant_title(job.get("title", "")):
                continue
            postings.append(Posting(
                source="arbeitnow", url=job["url"], title=job["title"], company=job.get("company_name", ""),
                location=job.get("location", ""), remote=bool(job.get("remote")),
                description=html_to_text(job.get("description")), posted_at=parse_date(job.get("created_at")),
            ))
        if not (data.get("links") or {}).get("next"):
            break
    return postings


def himalayas(client: httpx.Client, queries: list[str], countries: list[str], max_pages: int) -> list[Posting]:
    seen: dict[str, Posting] = {}
    for query in queries:
        for country in countries:
            for page in range(max_pages):
                data = get_with_retry(client, "https://himalayas.app/jobs/api/search", params={
                    "q": query, "country": country, "limit": 20, "offset": page * 20,
                }).json()
                jobs = data.get("jobs") or []
                for job in jobs:
                    seniority = set(job.get("seniority") or [])
                    if seniority and seniority <= _HIMALAYAS_TOO_SENIOR:
                        continue
                    if not is_relevant_title(job.get("title", "")) or job["guid"] in seen:
                        continue
                    regions = job.get("locationRestrictions") or ["Worldwide"]
                    seen[job["guid"]] = Posting(
                        source="himalayas", url=job["guid"], title=job["title"], company=job.get("companyName", ""),
                        location="Remote: " + ", ".join(regions), remote=True, remote_regions=regions,
                        description=html_to_text(job.get("description")), posted_at=parse_date(job.get("pubDate")),
                    )
                if len(jobs) < 20:
                    break
    return list(seen.values())


def remoteok(client: httpx.Client) -> list[Posting]:
    data = get_with_retry(client, "https://remoteok.com/api").json()
    postings = []
    for job in data[1:]:  # first element is the legal notice
        if not is_relevant_title(job.get("position", "")):
            continue
        location = job.get("location") or ""
        postings.append(Posting(
            source="remoteok", url=job["url"], title=job["position"], company=job.get("company", ""),
            location=f"Remote: {location or 'Worldwide'}", remote=True,
            remote_regions=[location] if location else ["Worldwide"],
            description=html_to_text(job.get("description")), posted_at=parse_date(job.get("date")),
        ))
    return postings

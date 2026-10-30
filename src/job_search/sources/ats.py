"""Public job feeds of hiring platforms used by the named companies (config/sources.yaml: ats).

Postings from these feeds are the employer's own listing (source_is_origin=True) and are proven
live by appearing in today's feed.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx

from job_search.models import Posting
from job_search.sources.base import get_with_retry, html_to_text, parse_date
from job_search.sources.relevance import is_relevant_title


def greenhouse(client: httpx.Client, company: str, slug: str) -> list[Posting]:
    data = get_with_retry(client, f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                          params={"content": "true"}).json()
    return [
        Posting(
            source="greenhouse", url=job["absolute_url"], title=job["title"], company=company,
            location=(job.get("location") or {}).get("name", ""),
            remote="remote" in (job.get("location") or {}).get("name", "").lower(),
            description=html_to_text(job.get("content")),
            posted_at=parse_date(job.get("first_published") or job.get("updated_at")),
            source_is_origin=True, ats="greenhouse", ats_job_id=str(job["id"]),
        )
        for job in data.get("jobs", [])
        if is_relevant_title(job.get("title", ""))
    ]


def ashby(client: httpx.Client, company: str, slug: str) -> list[Posting]:
    data = get_with_retry(client, f"https://api.ashbyhq.com/posting-api/job-board/{slug}").json()
    postings = []
    for job in data.get("jobs", []):
        if not job.get("isListed", True) or not is_relevant_title(job.get("title", "")):
            continue
        locations = [job.get("location") or ""] + [s.get("location", "") for s in job.get("secondaryLocations") or []]
        address = ((job.get("address") or {}).get("postalAddress") or {})
        location = "; ".join(loc for loc in locations if loc)
        if address.get("addressCountry") and address["addressCountry"] not in location:
            location = f"{location}; {address['addressCountry']}".strip("; ")
        postings.append(Posting(
            source="ashby", url=job["jobUrl"], title=job["title"], company=company,
            location=location, city=address.get("addressLocality"),
            remote=bool(job.get("isRemote")) or job.get("workplaceType") == "Remote" or "remote" in location.lower(),
            description=job.get("descriptionPlain") or html_to_text(job.get("descriptionHtml")),
            posted_at=parse_date(job.get("publishedAt")),
            source_is_origin=True, ats="ashby", ats_job_id=job["id"],
        ))
    return postings


def workable(client: httpx.Client, company: str, slug: str) -> list[Posting]:
    """List without details (the bulk details call is rate-limited), then fetch details per relevant job."""
    data = get_with_retry(client, f"https://apply.workable.com/api/v1/widget/accounts/{slug}").json()
    postings = []
    for job in data.get("jobs", []):
        if not is_relevant_title(job.get("title", "")):
            continue
        detail = get_with_retry(client, f"https://apply.workable.com/api/v2/accounts/{slug}/jobs/{job['shortcode']}").json()
        locs = job.get("locations") or [{"city": job.get("city"), "country": job.get("country"),
                                          "countryCode": None}]
        location = "; ".join(", ".join(x for x in (loc.get("city"), loc.get("country")) if x) for loc in locs)
        country = locs[0].get("countryCode") if len(locs) == 1 else None
        description = "\n".join(html_to_text(detail.get(k)) for k in ("description", "requirements", "benefits"))
        postings.append(Posting(
            source="workable", url=job["url"], title=job["title"], company=company,
            location=location, country=country, city=locs[0].get("city"),
            remote=bool(job.get("telecommuting")) or detail.get("workplace") == "remote",
            description=description.strip(), posted_at=parse_date(job.get("published_on")),
            source_is_origin=True, ats="workable", ats_job_id=job["shortcode"],
        ))
    return postings



def teamtailor(client: httpx.Client, company: str, slug: str) -> list[Posting]:
    root = ET.fromstring(get_with_retry(client, f"https://{slug}.teamtailor.com/jobs.rss").content)
    postings = []
    for item in root.iter("item"):
        title = item.findtext("title", "")
        if not is_relevant_title(title):
            continue
        places = []
        for loc in item.iter():
            if loc.tag.endswith("}location"):
                city = next((c.text for c in loc if c.tag.endswith("}city")), None)
                country = next((c.text for c in loc if c.tag.endswith("}country")), None)
                places.append(", ".join(x for x in (city, country) if x))
        link = item.findtext("link", "")
        postings.append(Posting(
            source="teamtailor", url=link, title=title, company=company,
            location="; ".join(places), remote=item.findtext("remoteStatus", "none") == "fully",
            description=html_to_text(item.findtext("description")),
            posted_at=parse_date(item.findtext("pubDate")),
            source_is_origin=True, ats="teamtailor", ats_job_id=item.findtext("guid") or link,
        ))
    return postings


def personio(client: httpx.Client, company: str, slug: str) -> list[Posting]:
    root = ET.fromstring(get_with_retry(client, f"https://{slug}.jobs.personio.de/xml",
                                        params={"language": "en"}).content)
    postings = []
    for pos in root.iter("position"):
        title = pos.findtext("name", "")
        if not is_relevant_title(title):
            continue
        offices = [pos.findtext("office", "")] + [o.text or "" for o in pos.findall("additionalOffices/office")]
        sections = [f"{d.findtext('name', '')}\n{html_to_text(d.findtext('value'))}"
                    for d in pos.findall("jobDescriptions/jobDescription")]
        years = pos.findtext("yearsOfExperience")
        if years:  # structured field -> sentence the seniority rule can read
            sections.append(f"Required experience: {years} years.")
        job_id = pos.findtext("id", "")
        postings.append(Posting(
            source="personio", url=f"https://{slug}.jobs.personio.de/job/{job_id}", title=title, company=company,
            location="; ".join(o for o in offices if o), description="\n".join(sections).strip(),
            posted_at=parse_date(pos.findtext("createdAt")),
            source_is_origin=True, ats="personio", ats_job_id=job_id,
        ))
    return postings


def lever(client: httpx.Client, company: str, slug: str, region: str = "global") -> list[Posting]:
    host = "api.eu.lever.co" if region == "eu" else "api.lever.co"
    jobs = get_with_retry(client, f"https://{host}/v0/postings/{slug}", params={"mode": "json"}).json()
    postings = []
    for job in jobs:
        if not is_relevant_title(job.get("text", "")):
            continue
        cats = job.get("categories") or {}
        locations = cats.get("allLocations") or [cats.get("location") or ""]
        lists = [f"{lst.get('text', '')}\n{html_to_text(lst.get('content'))}" for lst in job.get("lists") or []]
        description = "\n".join([job.get("descriptionPlain") or "", *lists, job.get("additionalPlain") or ""])
        location = "; ".join(loc for loc in locations if loc)
        postings.append(Posting(
            source="lever", url=job["hostedUrl"], title=job["text"], company=company, location=location,
            remote=job.get("workplaceType") == "remote" or "remote" in location.lower(),
            description=description.strip(), posted_at=parse_date(job.get("createdAt")),
            source_is_origin=True, ats="lever", ats_job_id=job["id"],
        ))
    return postings


def pinpoint(client: httpx.Client, company: str, slug: str) -> list[Posting]:
    data = get_with_retry(client, f"https://{slug}.pinpointhq.com/postings.json").json()
    postings = []
    for job in data.get("data", []):
        if not is_relevant_title(job.get("title", "")):
            continue
        loc = job.get("location") or {}
        location = ", ".join(x for x in (loc.get("city"), loc.get("name")) if x)
        sections = ("description", "key_responsibilities", "skills_knowledge_expertise", "benefits")
        description = "\n".join(html_to_text(job.get(k)) for k in sections if job.get(k))
        postings.append(Posting(
            source="pinpoint", url=job["url"], title=job["title"].strip(), company=company, location=location,
            remote=job.get("workplace_type") == "remote", description=description,
            source_is_origin=True, ats="pinpoint", ats_job_id=str(job["id"]),
        ))
    return postings


PLATFORMS = {
    "greenhouse": greenhouse,
    "ashby": ashby,
    "workable": workable,
    "teamtailor": teamtailor,
    "personio": personio,
    "lever": lever,
    "pinpoint": pinpoint,
}

"""Core data models shared by sources, verification, scoring and reporting."""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

VerdictStatus = Literal["pass", "fail", "flag"]


class Posting(BaseModel):
    """One job posting, normalised across sources."""

    source: str                       # e.g. "greenhouse", "arbeitnow", "discovery"
    url: str
    title: str
    company: str
    location: str = ""                # free text as given by the source
    country: str | None = None        # ISO-3166 alpha-2 if known
    city: str | None = None
    remote: bool = False
    remote_regions: list[str] = Field(default_factory=list)  # e.g. ["DE"], ["EMEA"], ["Worldwide"]
    description: str = ""             # plain text
    posted_at: date | None = None
    # True when `url` is the employer's own careers page / ATS listing (the original source).
    source_is_origin: bool = False
    # Set when the posting came from an ATS API that was fetched today (proves it is listed).
    ats: str | None = None
    ats_job_id: str | None = None

    @property
    def id(self) -> str:
        from job_search.dedup import normalize_url

        return hashlib.sha1(normalize_url(self.url).encode()).hexdigest()[:12]


class Verdict(BaseModel):
    """Result of one verification rule for one posting."""

    rule: str
    status: VerdictStatus
    reason: str = ""
    evidence: str = ""                # quoted snippet from the posting, if any

    @classmethod
    def ok(cls, rule: str, reason: str = "", evidence: str = "") -> Verdict:
        return cls(rule=rule, status="pass", reason=reason, evidence=evidence)

    @classmethod
    def fail(cls, rule: str, reason: str, evidence: str = "") -> Verdict:
        return cls(rule=rule, status="fail", reason=reason, evidence=evidence)

    @classmethod
    def flag(cls, rule: str, reason: str, evidence: str = "") -> Verdict:
        return cls(rule=rule, status="flag", reason=reason, evidence=evidence)


class VerificationResult(BaseModel):
    posting_id: str
    verdicts: list[Verdict]

    @property
    def passed(self) -> bool:
        return all(v.status != "fail" for v in self.verdicts)

    @property
    def failures(self) -> list[Verdict]:
        return [v for v in self.verdicts if v.status == "fail"]

    @property
    def flags(self) -> list[Verdict]:
        return [v for v in self.verdicts if v.status == "flag"]


_SOURCE_LABELS = {
    "indeed": "Indeed", "jobdatalake": "JobDataLake", "workable": "Workable", "linkedin": "LinkedIn",
    "arbeitnow": "Arbeitnow", "arbeitsagentur": "Bundesagentur für Arbeit", "himalayas": "Himalayas",
    "remoteok": "RemoteOK", "eures": "EURES", "bayt": "Bayt", "discovery": "web search",
    "greenhouse": "Greenhouse", "ashby": "Ashby", "teamtailor": "Teamtailor", "personio": "Personio",
    "lever": "Lever", "workday": "Workday", "smartrecruiters": "SmartRecruiters",
}
_COMPANY_PLATFORMS = {"greenhouse", "ashby", "teamtailor", "personio", "lever", "workday", "smartrecruiters"}


def source_label(source: str) -> str:
    """Human-readable source for reports: 'connector:indeed' -> 'Indeed'."""
    kind, _, detail = source.partition(":")
    if kind == "connector":
        return _SOURCE_LABELS.get(detail, detail)
    if kind == "jobspipe":
        boards = [_SOURCE_LABELS.get(b, b) for b in detail.split(",") if b and b != "unknown"]
        return f"{', '.join(boards)} (via JobsPipe)" if boards else "JobsPipe"
    if kind == "discovery":
        return f"web search ({detail})" if detail else "web search"
    if source in _COMPANY_PLATFORMS:
        return f"{_SOURCE_LABELS[source]} (company job board)"
    if source == "workable":
        return "Workable (company job board)"
    return _SOURCE_LABELS.get(source, source)

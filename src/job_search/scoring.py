"""Validates Claude's scores, cross-checks its extracted facts, and computes the final score.

The model judges (sub-scores, facts with quotes); every decision here is code.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from job_search.config import Criteria
from job_search.models import Posting, Verdict

RULE = "llm_crosscheck"
DESCRIPTION_LIMIT = 6000
_FLUENT_GERMAN = {"B2", "C1", "C2", "native"}

Score = Field(ge=0, le=100)


class SubScores(BaseModel):
    genai_relevance: int = Score
    skills_match: int = Score
    seniority_fit: int = Score
    domain_fit: int = Score
    growth: int = Score


class Facts(BaseModel):
    min_years: float | None = None
    requires_enrollment: bool = False
    german_level: Literal["none", "basic", "B1", "B2", "C1", "C2", "native", "unspecified"] = "unspecified"
    english_working_language: bool = False


class ScoreResult(BaseModel):
    posting_id: str
    sub_scores: SubScores
    facts: Facts
    evidence: dict[str, str] = Field(default_factory=dict)
    rationale: str = Field(default="", max_length=400)


def write_to_score(path: Path, ranked: list[tuple[Posting, float]]) -> None:
    items = [
        {"posting_id": p.id, "title": p.title, "company": p.company, "location": p.location, "url": p.url,
         "description": p.description[:DESCRIPTION_LIMIT]}
        for p, _ in ranked
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2))


def load_and_validate(path: Path, expected_ids: set[str]) -> tuple[dict[str, ScoreResult], list[str]]:
    """Valid results by posting id, plus human-readable problems (invalid, missing, unknown, duplicate)."""
    problems: list[str] = []
    if not path.exists():
        return {}, [f"{path} does not exist"]
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return {}, [f"{path} is not valid JSON: {exc}"]
    if not isinstance(raw, list):
        return {}, [f"{path} must contain a JSON array"]

    results: dict[str, ScoreResult] = {}
    for i, item in enumerate(raw):
        try:
            result = ScoreResult.model_validate(item)
        except ValidationError as exc:
            pid = item.get("posting_id", f"#{i}") if isinstance(item, dict) else f"#{i}"
            problems.append(f"{pid}: invalid ({exc.error_count()} errors: {exc.errors()[0]['loc']} {exc.errors()[0]['msg']})")
            continue
        if result.posting_id not in expected_ids:
            problems.append(f"{result.posting_id}: not in to_score.json")
        elif result.posting_id in results:
            problems.append(f"{result.posting_id}: scored twice")
        else:
            results[result.posting_id] = result
    for pid in sorted(expected_ids - results.keys()):
        if not any(pr.startswith(pid) for pr in problems):
            problems.append(f"{pid}: missing")
    return results, problems


def _quote_in_text(quote: str, text: str) -> bool:
    norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()  # noqa: E731
    q = norm(quote)
    return len(q) >= 8 and q in norm(text)


def cross_check(result: ScoreResult, posting: Posting, criteria: Criteria) -> list[Verdict]:
    """Compare the model's extracted facts with the hard criteria.

    A fact that violates a criterion excludes the posting only when its evidence quote is found
    verbatim in the posting text; otherwise it becomes a flag. Facts never change sub-scores.
    """
    facts, ev = result.facts, result.evidence
    claims: list[tuple[str, str]] = []
    if facts.min_years is not None and facts.min_years > criteria.max_min_years:
        claims.append((f"model reports {facts.min_years:g}+ years required", ev.get("min_years", "")))
    if facts.requires_enrollment:
        claims.append(("model reports university enrollment required", ev.get("requires_enrollment", "")))
    if facts.german_level in _FLUENT_GERMAN and not facts.english_working_language:
        claims.append((f"model reports German {facts.german_level} required", ev.get("german_level", "")))

    text = f"{posting.title}\n{posting.description}"
    verdicts = []
    for reason, quote in claims:
        if _quote_in_text(quote, text):
            verdicts.append(Verdict.fail(RULE, reason, quote))
        else:
            verdicts.append(Verdict.flag(RULE, f"{reason}, but its quote was not found in the posting — check", quote))
    return verdicts


def final_score(result: ScoreResult, bonus: float, criteria: Criteria) -> float:
    weights = criteria.weights.model_dump()
    weighted = sum(getattr(result.sub_scores, k) * w for k, w in weights.items())
    return round(min(100.0, max(0.0, weighted + bonus)), 1)

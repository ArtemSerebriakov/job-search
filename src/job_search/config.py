"""Loads config/criteria.yaml and config/profile.md."""

from __future__ import annotations

import os
import re
from functools import cached_property
from pathlib import Path

import yaml
from pydantic import BaseModel, model_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"
LOGS_DIR = PROJECT_ROOT / "logs"

_LEGAL_SUFFIXES = re.compile(
    r"\b(gmbh|ag|se|kg|ug|bv|b\.v\.|nv|n\.v\.|ltd|limited|inc|llc|plc|corp|corporation|co|fz-llc|fzco|group|holding|holdings)\b\.?",
    re.IGNORECASE,
)


def normalize_company(name: str) -> str:
    """Lowercase, drop legal suffixes and punctuation: 'EPAM Systems, Inc.' -> 'epam systems'."""
    s = _LEGAL_SUFFIXES.sub(" ", name.lower())
    s = re.sub(r"[^\w.]+", " ", s)
    return re.sub(r"\s+", " ", s).strip(" .")


class Weights(BaseModel):
    genai_relevance: float
    skills_match: float
    seniority_fit: float
    domain_fit: float
    growth: float

    @model_validator(mode="after")
    def _sum_to_one(self) -> Weights:
        total = sum(self.model_dump().values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"weights must sum to 1.0, got {total}")
        return self


class Calibration(BaseModel):
    min_resolved: int = 30
    no_reply_after_days: int = 45
    default_reply_rate: float = 0.08


class Criteria(BaseModel):
    named_companies: dict[str, list[str]]
    allowed_countries: list[str]
    location_bonus: dict[str, float]
    max_min_years: int = 2
    weights: Weights
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    prefilter_top_k: int = 25
    digest_size: int = 10
    min_final_score: float = 55
    calibration: Calibration = Calibration()

    model_config = {"ignored_types": (cached_property,)}

    @cached_property
    def _company_index(self) -> dict[str, str]:
        index: dict[str, str] = {}
        for canonical, aliases in self.named_companies.items():
            for name in [canonical, *(aliases or [])]:
                index[normalize_company(name)] = canonical
        return index

    def match_named_company(self, company: str) -> str | None:
        """Return the canonical named company for `company`, or None.

        Matches the full normalised name, or a normalised alias as a whole-word prefix
        ("Revolut Business" -> Revolut), never a substring inside another word.
        """
        norm = normalize_company(company)
        if not norm:
            return None
        if norm in self._company_index:
            return self._company_index[norm]
        for alias, canonical in self._company_index.items():
            if re.match(rf"{re.escape(alias)}\b", norm):
                return canonical
        return None


def load_env(path: Path | None = None) -> None:
    """Load KEY=VALUE lines from the git-ignored .env into os.environ (existing variables win)."""
    path = path or PROJECT_ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def load_criteria(path: Path | None = None) -> Criteria:
    path = path or CONFIG_DIR / "criteria.yaml"
    return Criteria.model_validate(yaml.safe_load(path.read_text()))


def load_profile(path: Path | None = None) -> str:
    """Your CV text: config/profile.md (git-ignored, personal), else the committed example."""
    if path is None:
        path = CONFIG_DIR / "profile.md"
        if not path.exists():
            path = CONFIG_DIR / "profile.example.md"
    return path.read_text()


def digest_recipient() -> str | None:
    """The only address the daily email may go to: DIGEST_RECIPIENT in .env."""
    return os.environ.get("DIGEST_RECIPIENT") or None

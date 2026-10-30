"""Builds the list of sources to run from config/sources.yaml."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path

import httpx
import yaml

from job_search.config import CONFIG_DIR
from job_search.models import Posting
from job_search.sources import ats, boards, jobspipe


def load_sources_config(path: Path | None = None) -> dict:
    return yaml.safe_load((path or CONFIG_DIR / "sources.yaml").read_text())


def build_sources(client: httpx.Client, config: dict) -> list[tuple[str, Callable[[], list[Posting]]]]:
    sources: list[tuple[str, Callable[[], list[Posting]]]] = []
    for entry in config.get("ats", []):
        fetch = ats.PLATFORMS[entry["platform"]]
        extra = {"region": entry["region"]} if "region" in entry else {}
        sources.append((f"{entry['platform']}:{entry['slug']}",
                        partial(fetch, client, entry["company"], entry["slug"], **extra)))
    if ba := config.get("arbeitsagentur"):
        sources.append(("arbeitsagentur", partial(boards.arbeitsagentur, client, ba["queries"],
                                                  ba["published_within_days"], ba["max_pages"])))
    if an := config.get("arbeitnow"):
        sources.append(("arbeitnow", partial(boards.arbeitnow, client, an["max_pages"])))
    if hm := config.get("himalayas"):
        sources.append(("himalayas", partial(boards.himalayas, client, hm["queries"], hm["countries"], hm["max_pages"])))
    if (config.get("remoteok") or {}).get("enabled"):
        sources.append(("remoteok", partial(boards.remoteok, client)))
    if jp := config.get("jobspipe"):
        sources.append(("jobspipe", partial(jobspipe.fetch, client, jp["searches"], jp["max_results_per_day"])))
    return sources

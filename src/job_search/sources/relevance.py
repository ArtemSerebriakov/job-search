"""Cheap title pre-filter applied at collection time, before anything is stored.

Keeps only titles in the target field. This is a volume filter, not an eligibility rule:
eligibility (seniority, student roles, language, location) is decided in verify/.
"""

from __future__ import annotations

import re

_FIELD = re.compile(
    r"(\bai\b|\ba\.i\.|\bki\b|\bml\b|mlops|\bllms?\b|\bnlp\b|gen\s?ai|machine[- ]learning|maschinelles lernen|"
    r"deep[- ]learning|data[- ]scien\w*|data[- ]analy\w*|data[- ]engineer\w*|\bdata\b.{0,20}\b(graduate|junior|trainee)|"
    r"applied[- ]scien\w*|research[- ]scien\w*|research[- ]engineer|computer[- ]vision|artificial intelligence|"
    r"künstliche intelligenz|kuenstliche intelligenz|\bscientist\b|prompt engineer|"
    r"natural language|language model|generative|reinforcement learning|\brag\b|retrieval|recommend\w* system)",
    re.IGNORECASE,
)
# Graduate programmes in broader software engineering are wanted too.
_GRADUATE_SWE = re.compile(
    r"\b(graduate|new grad|trainee|absolvent\w*|berufseinsteiger\w*|early[- ]career|entry[- ]level|junior)\b"
    r".{0,40}\b(engineer\w*|developer|entwickler\w*|scientist|analyst|programme|program)\b",
    re.IGNORECASE,
)


def is_relevant_title(title: str) -> bool:
    title = title or ""
    return bool(_FIELD.search(title) or _GRADUATE_SWE.search(title))

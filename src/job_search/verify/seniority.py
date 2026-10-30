"""Rule: only graduate / junior / associate / early-career roles (0-2 years).

Years of experience are extracted deterministically. Per sentence the *minimum* number counts
(alternatives like "Master's + 1 year or Bachelor's + 3 years"); across sentences the *maximum*
counts; nice-to-have sentences are ignored.
"""

from __future__ import annotations

import re

from job_search.models import Posting, Verdict
from job_search.verify.text import is_optional, sentences

RULE = "seniority"

_SENIOR_TITLE = re.compile(
    r"\b(senior|sr\.?|snr|lead|leading|staff|principal|head|manager|management|director|vp|"
    r"vice president|chief|mid[- ]?level|mid[- ]?senior|mid|intermediate|expert|experienced|"
    r"architect|\w*leiter\w*|\w*leitung|teamlead\w*|führungskraft|middle|co-?founder|cto|ceo|cfo|coo|"
    r"consultant iii?|ii|iii|iv|l[4-9])\b",
    re.IGNORECASE,
)
_ENTRY_TITLE = re.compile(
    r"\b(junior|jr\.?|graduate|grad|new grad|entry[- ]level|entry|associate|early[- ]career|"
    r"berufseinsteiger\w*|absolvent\w*|einsteiger\w*|trainee|apprentice|residency|resident|fellow(ship)?|"
    r"starter|young professional|rotational|i)\b",
    re.IGNORECASE,
)
_HIGH_YEARS_ASSOCIATE_CONTEXT = re.compile(
    r"\b(consult\w*|bank\w*|investment|private equity|m&a|law firm|legal|lawyer|attorney|audit\w*|"
    r"advisory|mba|transaction services|corporate finance)\b",
    re.IGNORECASE,
)

_NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "a": 1, "an": 1,
    "ein": 1, "eine": 1, "einem": 1, "einer": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "fuenf": 5,
    "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "mehrere": 3, "mehrjährige": 3,
    "several": 3, "multiple": 3,
}
_NUM = r"\b(\d{1,2}(?:[.,]5)?|" + "|".join(sorted(_NUM_WORDS, key=len, reverse=True)) + r")"
_YEARS = r"(?:years?|yrs?|jahre?n?|jahr)"
_EXPERIENCE = r"(?:experience|exp\.?|erfahrung|berufserfahrung|praxiserfahrung|work(?:ing)? in|working with|hands-on|track record|industry)"

# "3+ years of experience", "2-4 years experience", "at least 3 years in", "mindestens 3 Jahre Berufserfahrung"
_PATTERN_NUM_FIRST = re.compile(
    rf"(?:at least|minimum(?: of)?|min\.?|mindestens|over|more than|mehr als|über|ueber)?\s*"
    rf"{_NUM}\s*(?:\+|plus)?\s*(?:(?:-|–|to|bis|or)\s*{_NUM}\s*\+?\s*)?{_YEARS}\b[^.;\n]{{0,60}}?{_EXPERIENCE}",
    re.IGNORECASE,
)
# "experience of 3+ years", "Berufserfahrung von mindestens 3 Jahren", "erste Berufserfahrung (1-2 Jahre)"
_PATTERN_EXP_FIRST = re.compile(
    rf"{_EXPERIENCE}[^.;\n]{{0,60}}?(?:of|von|from|\()?\s*(?:at least|minimum(?: of)?|mindestens|over|more than|mehr als)?\s*"
    rf"{_NUM}\s*(?:\+|plus)?\s*(?:(?:-|–|to|bis)\s*{_NUM}\s*\+?\s*)?{_YEARS}\b",
    re.IGNORECASE,
)
# "mehrjährige Berufserfahrung", "several years of experience", "extensive experience"
_VAGUE_MULTI_YEAR = re.compile(
    r"\b(mehrjährige\w*|langjährige\w*|several years|many years|multiple years)\b[^.;\n]{0,30}?"
    r"(experience|erfahrung|berufserfahrung|praxiserfahrung)|"
    r"\b(extensive|significant|substantial) (professional |industry |hands-on )?experience\b",
    re.IGNORECASE,
)
# A senior-level experience requirement stated in words rather than years.
_SENIOR_BODY = re.compile(
    r"\bsenior[- ]level\b|\bexperience as an? senior\b|\berfahrung als senior\b",
    re.IGNORECASE,
)
# Benefit sentences that mention years but are not requirements ("30 days holiday", "founded 10 years ago").
_NOT_A_REQUIREMENT = re.compile(r"\b(ago|founded|since|history|anniversary|days|vacation|urlaub|old)\b", re.IGNORECASE)


def _to_number(token: str) -> float:
    token = token.lower().replace(",", ".")
    return float(token) if token[0].isdigit() else float(_NUM_WORDS[token])


def required_years(text: str) -> tuple[float | None, str]:
    """Deterministic minimum-years requirement of a posting and the sentence that sets it."""
    best: float | None = None
    best_sentence = ""
    for sentence in sentences(text):
        if is_optional(sentence) or _NOT_A_REQUIREMENT.search(sentence):
            continue
        values: list[float] = []
        for pattern in (_PATTERN_NUM_FIRST, _PATTERN_EXP_FIRST):
            for m in pattern.finditer(sentence):
                values.append(_to_number(m.group(1)))  # lower bound of a range
        if not values:
            if _VAGUE_MULTI_YEAR.search(sentence):
                values.append(3.0)
            else:
                continue
        sentence_min = min(values)
        if best is None or sentence_min > best:
            best, best_sentence = sentence_min, sentence
    return best, best_sentence


def check(posting: Posting, max_min_years: int = 2) -> Verdict:
    title = posting.title
    m = _SENIOR_TITLE.search(title)
    if m:
        return Verdict.fail(RULE, f"senior-level title ('{m.group(0)}')", title)

    for sentence in sentences(posting.description):
        if not is_optional(sentence) and _SENIOR_BODY.search(sentence):
            return Verdict.fail(RULE, "requires senior-level experience", sentence)

    years, evidence = required_years(posting.description)
    if years is not None and years > max_min_years:
        return Verdict.fail(RULE, f"requires {years:g}+ years of experience (max {max_min_years})", evidence)

    entry = _ENTRY_TITLE.search(title)
    if entry and entry.group(0).lower() == "associate":
        context = f"{posting.company} {title} {posting.description}"
        if _HIGH_YEARS_ASSOCIATE_CONTEXT.search(context) and years is None:
            return Verdict.fail(
                RULE,
                "'Associate' in a consulting/banking/law context without an explicit ≤2-year requirement",
                title,
            )

    if years is not None:
        return Verdict.ok(RULE, f"requires {years:g} years (≤ {max_min_years})", evidence)
    if entry:
        return Verdict.ok(RULE, f"entry-level title ('{entry.group(0)}')", title)
    return Verdict.flag(RULE, "seniority not stated in title or body — check before applying", title)

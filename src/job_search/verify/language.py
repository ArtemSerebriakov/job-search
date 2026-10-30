"""Rule: no German / Dutch / Arabic fluency requirement unless English is the working language.

The language the description itself is written in is checked separately (description_language.py).
"""

from __future__ import annotations

import re

from job_search.models import Posting, Verdict
from job_search.verify.text import is_optional, sentences

RULE = "language"

_LANG = r"(german|deutsch\w*|dutch|nederlands|arabic)"
# Levels that on their own mean "fluent" (B2 and above).
_STRICT = r"(fluent|fluency|fließend\w*|fliessend\w*|verhandlungssicher\w*|business[- ]fluent|business[- ]level|" \
          r"native|muttersprach\w*|upper[- ]intermediate|advanced|c1|c2|b2)"
# Generic quality words: count only when attached to a language noun ("very good German skills").
_GENERIC = r"(excellent|very good|strong|proficient|professional|good|gute?n?|sehr gute?n?|exzellente?n?|hervorragende?n?)"
_LANG_NOUN = r"(german|deutsch|dutch|nederlands|arabic)[- ]?(language|skills|proficiency|speaker|speaking|" \
             r"kenntnisse|sprachkenntnisse|sprache|communication)"
_REQUIRE_PATTERNS = [
    re.compile(rf"\b{_STRICT}\b[^.;\n]{{0,40}}?\b{_LANG}", re.IGNORECASE),        # "fluent in English and German"
    re.compile(rf"\b{_LANG}\b[^.;\n]{{0,20}}?\b{_STRICT}\b", re.IGNORECASE),      # "German (C1)", "Deutsch fließend"
    re.compile(rf"\b{_GENERIC}\b[^.;\n]{{0,25}}?\b{_LANG_NOUN}", re.IGNORECASE),   # "sehr gute Deutschkenntnisse"
    re.compile(rf"\b{_LANG}[- ]?(language|skills|kenntnisse|sprachkenntnisse)?\b[^.;\n]{{0,25}}?\b(is |are )?"
               rf"(required|mandatory|a must|essential|zwingend|erforderlich|vorausgesetzt)\b", re.IGNORECASE),
    re.compile(r"\b(deutsch- und englischkenntnisse|deutsch und englisch)\b", re.IGNORECASE),
]
# A lower level attached to the language ("basic German", "German B1") is not a fluency requirement.
_WEAK = re.compile(rf"\b(basic|grundkenntnisse|grundlegende?|a1|a2|b1|beginner|elementary|some)\b[^.;\n]{{0,15}}?{_LANG}|"
                   rf"{_LANG}\w*\s*(\(|:|-)?\s*(a1|a2|b1|basic|grundkenntnisse)\b", re.IGNORECASE)
# Below fluency but above beginner: a required intermediate/B1 level is flagged, not failed.
_MID = r"(intermediate\+?|b1\+?|conversational|working knowledge|gute?n?)"
_MID_PATTERNS = [
    re.compile(rf"\b{_MID}[^.;\n]{{0,25}}?\b{_LANG}", re.IGNORECASE),     # "Intermediate German", "working knowledge of German"
    re.compile(rf"\b{_LANG}\b[^.;\n]{{0,25}}?\b{_MID}", re.IGNORECASE),  # "Level of German – from Intermediate+", "German B1"
]

_ENGLISH_WORKING = re.compile(
    r"(working language (is|will be) english|english is (our|the) (working|company|official|main|everyday|day-to-day) language|"
    r"(company|working|office|team|corporate) language (is )?english|"
    r"english[- ]speaking (team|environment|company|workplace|office)|international,? english[- ]speaking|"
    r"arbeitssprache( ist)? englisch|unternehmenssprache( ist)? englisch|"
    r"(no|without) (need for |)german|german (is )?not (required|necessary|needed)|"
    r"keine deutschkenntnisse (erforderlich|notwendig|nötig))",
    re.IGNORECASE,
)


def language_required(text: str) -> tuple[str | None, str]:
    """Return (matched requirement, sentence) for the first mandatory local-language requirement."""
    for sentence in sentences(text):
        if is_optional(sentence):
            continue
        for pattern in _REQUIRE_PATTERNS:
            m = pattern.search(sentence)
            if m and not _WEAK.search(sentence[m.start(): m.end() + 20]):
                return m.group(0), sentence
    return None, ""


def check(posting: Posting) -> Verdict:
    text = f"{posting.title}\n{posting.description}"
    english = _ENGLISH_WORKING.search(text)
    requirement, sentence = language_required(text)
    if requirement:
        if english:
            return Verdict.ok(RULE, "local language mentioned but English is the working language", english.group(0))
        return Verdict.fail(RULE, f"requires local-language fluency ('{requirement}')", sentence)
    middle, sentence = intermediate_required(text)
    if middle and not english:
        return Verdict.flag(RULE, f"asks for intermediate German ('{middle}') — above beginner level, check", sentence)
    return Verdict.ok(RULE)


def intermediate_required(text: str) -> tuple[str | None, str]:
    for sentence in sentences(text):
        if is_optional(sentence):
            continue
        for pattern in _MID_PATTERNS:
            m = pattern.search(sentence)
            if m:
                return m.group(0), sentence
    return None, ""

"""Rule: the posting description must be written in English or Russian.

Deterministic detection, no model: Cyrillic/Arabic by script, Latin-script languages by counting
function words that belong to exactly one language. A bilingual posting passes when it carries a
substantial English (or Russian) part.
"""

from __future__ import annotations

import re
from collections import Counter

from job_search.models import Posting, Verdict

RULE = "description_language"

ALLOWED = {"en", "ru"}
MIN_FUNCTION_WORDS = 15      # fewer hits than this: too little text to judge -> flag
MIN_ALLOWED_SHARE = 0.4      # share of function-word hits that must be English (bilingual postings)

_RAW_STOPWORDS = {
    "en": "the and to of for with you we our your are will be on as at this that an or from have "
          "they their who what which about would should can into than more within team",
    "de": "und der die das mit für wir sie du ist sind bei auf uns dein deine deinen ihre ihr eine einen "
          "ein zu von im den dem nicht oder auch als wie bietet bieten wird werden unser unsere unseren",
    "nl": "het een van en voor met wij jij je ons onze bij zijn op aan naar ook niet jouw wat hebt heb "
          "bent worden wordt",
    "fr": "le la les et des pour avec nous vous une est sont dans sur au aux du que qui votre notre vos "
          "nos ce cette être",
    "es": "el los las y para con nosotros una es son por que tu tus nuestro nuestra del sus somos tienes",
    "it": "il lo gli e di per con noi è sono nel della che tuo tua nostro nostra sei siamo",
    "pt": "os e para com nós uma é são em por seu sua nosso nossa do da você somos",
    "pl": "i w z na do że jest są dla oraz się nie od jak przez będziesz oferujemy",
    "tr": "ve bir bu için ile olarak olan çok gibi",
    "uz": "va bilan uchun bu bo'yicha ham yoki",
}


def _exclusive_stopwords() -> dict[str, frozenset[str]]:
    """Keep only words that belong to a single language, so shared words can't tip the count."""
    owners = Counter(w for words in _RAW_STOPWORDS.values() for w in set(words.split()))
    return {lang: frozenset(w for w in words.split() if owners[w] == 1) for lang, words in _RAW_STOPWORDS.items()}


_STOPWORDS = _exclusive_stopwords()
_WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?", re.UNICODE)
_CYRILLIC = re.compile(r"[а-яёіїєґәғқңөұүһ]", re.IGNORECASE)
_NON_RUSSIAN_CYRILLIC = re.compile(r"[іїєґәғқңөұүһ]", re.IGNORECASE)   # Ukrainian / Kazakh letters
_ARABIC = re.compile(r"[؀-ۿ]")
_LATIN = re.compile(r"[a-zà-öø-ÿāăąćčďęěğıłńňőřśşšţťůűźżž]", re.IGNORECASE)


def detect(text: str) -> tuple[str | None, str]:
    """Return (language code or None if undetermined, short explanation)."""
    cyr, arab, lat = len(_CYRILLIC.findall(text)), len(_ARABIC.findall(text)), len(_LATIN.findall(text))
    letters = cyr + arab + lat
    if letters < 80:
        return None, f"only {letters} letters of text"
    if arab / letters > 0.3:
        return "ar", "Arabic script"
    if cyr / letters > 0.3:
        non_ru = len(_NON_RUSSIAN_CYRILLIC.findall(text))
        if non_ru / cyr > 0.01:
            return "uk/kk", f"Cyrillic with {non_ru} Ukrainian/Kazakh letters"
        return "ru", "Russian (Cyrillic)"

    hits = Counter()
    for word in _WORD.findall(text.lower()):
        for lang, words in _STOPWORDS.items():
            if word in words:
                hits[lang] += 1
    total = sum(hits.values())
    if total < MIN_FUNCTION_WORDS:
        return None, f"only {total} function words"
    if hits["en"] / total >= MIN_ALLOWED_SHARE:
        return "en", f"English {hits['en']}/{total} function words"
    top, count = hits.most_common(1)[0]
    return top, f"{top} {count}/{total} function words, English {hits['en']}/{total}"


def check(posting: Posting) -> Verdict:
    text = posting.description.strip()
    if not text:
        return Verdict.flag(RULE, "no description text to check the language")
    lang, why = detect(text)
    if lang is None:
        return Verdict.flag(RULE, f"description too short to determine its language ({why})")
    if lang in ALLOWED:
        return Verdict.ok(RULE, f"description language: {lang}", why)
    return Verdict.fail(RULE, f"description is not in English or Russian (detected {lang})", why)

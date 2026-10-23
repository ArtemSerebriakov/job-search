"""Rule: named companies are eligible anywhere; everyone else only in DE / NL / AE."""

from __future__ import annotations

import re

from job_search.config import Criteria
from job_search.models import Posting, Verdict

RULE = "location"

# Lowercase keyword -> ISO country. Cities first so the specific match wins in evidence.
_PLACES: dict[str, str] = {
    # Germany
    "munich": "DE", "münchen": "DE", "muenchen": "DE", "berlin": "DE", "hamburg": "DE",
    "frankfurt": "DE", "cologne": "DE", "köln": "DE", "koeln": "DE", "stuttgart": "DE",
    "düsseldorf": "DE", "duesseldorf": "DE", "dusseldorf": "DE", "leipzig": "DE", "dresden": "DE",
    "hannover": "DE", "hanover": "DE", "nuremberg": "DE", "nürnberg": "DE", "nuernberg": "DE",
    "karlsruhe": "DE", "heidelberg": "DE", "mannheim": "DE", "bonn": "DE", "essen": "DE",
    "dortmund": "DE", "bremen": "DE", "aachen": "DE", "darmstadt": "DE", "wolfsburg": "DE",
    "ingolstadt": "DE", "potsdam": "DE", "freiburg": "DE", "augsburg": "DE", "regensburg": "DE",
    "garching": "DE", "bielefeld": "DE", "mainz": "DE", "wiesbaden": "DE", "münster": "DE",
    "germany": "DE", "deutschland": "DE",
    # Netherlands
    "amsterdam": "NL", "rotterdam": "NL", "utrecht": "NL", "eindhoven": "NL", "the hague": "NL",
    "den haag": "NL", "delft": "NL", "leiden": "NL", "groningen": "NL", "haarlem": "NL",
    "amstelveen": "NL", "hoofddorp": "NL", "nijmegen": "NL", "tilburg": "NL", "arnhem": "NL",
    "enschede": "NL", "netherlands": "NL", "nederland": "NL", "holland": "NL",
    # UAE
    "dubai": "AE", "abu dhabi": "AE", "sharjah": "AE", "ajman": "AE", "ras al khaimah": "AE",
    "united arab emirates": "AE", "uae": "AE", "u.a.e": "AE",
}
_PLACE_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in sorted(_PLACES, key=len, reverse=True)) + r")\b",
                       re.IGNORECASE)
# Remote regions that include Germany or the Netherlands.
_REGIONS_COVERING = re.compile(
    r"\b(europe|european union|\beu\b|eea|emea|dach|benelux|cet|worldwide|anywhere|global)\b", re.IGNORECASE
)
# Places clearly outside DE/NL/AE: a match here is a confident FAIL; an unrecognised place only FLAGs.
_FOREIGN = re.compile(
    r"\b(united kingdom|uk|england|london|manchester|edinburgh|united states|usa|us|new york|san francisco|"
    r"seattle|boston|austin|canada|toronto|vancouver|france|paris|spain|madrid|barcelona|portugal|lisbon|"
    r"poland|warsaw|krakow|kraków|wroclaw|czech|prague|austria|vienna|wien|switzerland|zurich|zürich|geneva|"
    r"basel|bern|lausanne|lugano|zug|belgium|brussels|ireland|dublin|italy|milan|rome|sweden|stockholm|denmark|copenhagen|norway|oslo|"
    r"finland|helsinki|estonia|tallinn|latvia|riga|lithuania|vilnius|romania|bucharest|bulgaria|sofia|"
    r"hungary|budapest|serbia|belgrade|montenegro|cyprus|limassol|nicosia|greece|athens|turkey|istanbul|"
    r"georgia|tbilisi|armenia|yerevan|kazakhstan|almaty|astana|uzbekistan|tashkent|kyrgyzstan|bishkek|"
    r"israel|tel aviv|india|bangalore|bengaluru|hyderabad|pune|singapore|hong kong|japan|tokyo|china|"
    r"brazil|mexico|argentina|saudi arabia|riyadh|qatar|doha|bahrain|egypt|cairo|ukraine|kyiv|moldova|"
    r"luxembourg|malta|slovakia|slovenia|croatia|australia|sydney)\b",
    re.IGNORECASE,
)
_MUNICH = re.compile(r"\b(munich|münchen|muenchen|garching)\b", re.IGNORECASE)


def countries_in(text: str) -> list[str]:
    seen: list[str] = []
    for m in _PLACE_RE.finditer(text or ""):
        c = _PLACES[m.group(1).lower()]
        if c not in seen:
            seen.append(c)
    return seen


def posting_countries(posting: Posting) -> list[str]:
    countries = [posting.country.upper()] if posting.country else []
    for c in countries_in(f"{posting.city or ''} {posting.location}"):
        if c not in countries:
            countries.append(c)
    return countries


def is_munich(posting: Posting) -> bool:
    return bool(_MUNICH.search(f"{posting.city or ''} {posting.location}"))


def check(posting: Posting, criteria: Criteria) -> Verdict:
    named = criteria.match_named_company(posting.company)
    if named:
        return Verdict.ok(RULE, f"named company ({named}): any location eligible", posting.location)

    allowed = set(criteria.allowed_countries)
    countries = posting_countries(posting)
    hits = [c for c in countries if c in allowed]
    if hits:
        return Verdict.ok(RULE, f"located in {', '.join(hits)}", posting.location)

    if posting.remote:
        regions = [r.upper() for r in posting.remote_regions]
        if set(regions) & allowed or set(countries_in(" ".join(posting.remote_regions))) & allowed:
            return Verdict.ok(RULE, "remote, open to an allowed country", ", ".join(posting.remote_regions))
        region_text = " ".join(posting.remote_regions) or posting.location
        if _REGIONS_COVERING.search(region_text):
            return Verdict.flag(RULE, "remote within a region that includes Germany/Netherlands — confirm eligibility",
                                region_text)
        if countries or _FOREIGN.search(region_text):
            return Verdict.fail(RULE, "remote but restricted to countries outside DE/NL/AE", region_text)
        return Verdict.flag(RULE, "remote, eligible countries not stated", region_text)

    if not countries:
        place = f"{posting.city or ''} {posting.location}".strip()
        if not place:
            return Verdict.flag(RULE, "location not stated")
        if _FOREIGN.search(place):
            return Verdict.fail(RULE, "location not in Germany, Netherlands or UAE", place)
        return Verdict.flag(RULE, "location not recognised — check it is in Germany, Netherlands or UAE", place)
    return Verdict.fail(RULE, f"location {', '.join(countries)} not in Germany, Netherlands or UAE", posting.location)


def location_bonus(posting: Posting, criteria: Criteria) -> float:
    bonus = criteria.location_bonus
    if is_munich(posting):
        return bonus.get("munich", 0.0)
    for c in criteria.allowed_countries:
        if c in posting_countries(posting):
            return bonus.get(c, 0.0)
    return bonus.get("other", 0.0)

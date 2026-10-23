"""Rule: the posting must still be open, verified on the original source.

`classify` is pure and fully tested; `check` does the HTTP request through an injectable client.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

import httpx

from job_search.models import Posting, Verdict, source_label
from job_search.verify.link import check as check_link

RULE = "liveness"

_CLOSED = re.compile(
    r"(no longer (accepting|available|active|open)|not accepting applications|position (has been|is) (filled|closed)|"
    r"(job|position|vacancy|posting|role) (is )?(closed|expired|no longer exists|has expired|not found)|"
    r"this job (has )?(expired|closed)|applications? (are |is )?closed|job not found|page not found|"
    r"(diese )?stelle ist (nicht mehr|bereits) (verfügbar|besetzt|vergeben)|stellenanzeige (ist )?(nicht mehr|abgelaufen)|"
    r"nicht mehr verfügbar|bereits besetzt|vacature is (gesloten|niet meer beschikbaar)|sorry, this job)",
    re.IGNORECASE,
)
_UNAVAILABLE = {401, 403, 429, 500, 502, 503, 504}


def classify(posting: Posting, status_code: int, final_url: str, text: str) -> Verdict:
    """Decide liveness from an HTTP response for the posting URL."""
    if status_code in (404, 410):
        return Verdict.fail(RULE, f"HTTP {status_code}: posting removed", posting.url)
    if status_code in _UNAVAILABLE or status_code >= 400:
        if posting.source.startswith(("connector:", "jobspipe:")):
            # The board blocks automated checks, but its own search returned the posting as live today.
            return Verdict.flag(RULE, f"Live on {source_label(posting.source)} today; employer page not checked",
                                posting.url)
        return Verdict.flag(RULE, f"Could not open the posting page (HTTP {status_code}) — check it manually",
                            posting.url)
    m = _CLOSED.search(text[:20000])
    if m:
        return Verdict.fail(RULE, "page says the posting is closed", m.group(0))
    if final_url and _redirected_to_listing(posting.url, final_url):
        return Verdict.fail(RULE, "redirects to a careers listing page (posting removed)", final_url)
    if not posting.source_is_origin:
        return Verdict.flag(RULE, f"Confirmed live on {source_label(posting.source)}, not on the employer's own site "
                                  "— check the company site before applying", posting.url)
    return Verdict.ok(RULE, "page is live on the original source", final_url or posting.url)


def _redirected_to_listing(original: str, final: str) -> bool:
    o, f = urlsplit(original), urlsplit(final)
    if (o.netloc, o.path.rstrip("/")) == (f.netloc, f.path.rstrip("/")):
        return False
    probe = Posting(source="probe", url=final, title="", company="")
    return check_link(probe).status == "fail"


def check(posting: Posting, client: httpx.Client) -> Verdict:
    # A posting returned by the employer's ATS API in today's collect run is listed right now.
    if posting.ats and posting.ats_job_id and posting.source_is_origin:
        return Verdict.ok(RULE, f"listed in the {posting.ats} API today", posting.url)
    try:
        resp = client.get(posting.url, follow_redirects=True, timeout=20)
    except httpx.HTTPError as exc:
        return Verdict.flag(RULE, f"could not reach the page ({type(exc).__name__}); check manually", posting.url)
    return classify(posting, resp.status_code, str(resp.url), resp.text)

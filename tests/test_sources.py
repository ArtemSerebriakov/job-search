from pathlib import Path

import httpx
import pytest

from job_search.sources import ats, boards
from job_search.sources.base import html_to_text, run_source
from job_search.sources.relevance import is_relevant_title

FIXTURES = Path(__file__).parent / "fixtures"


def client_for(routes: dict[str, str]) -> httpx.Client:
    """MockTransport client: first route whose key is a substring of the URL serves that fixture."""
    def handler(request: httpx.Request) -> httpx.Response:
        for key, name in routes.items():
            if key in str(request.url):
                return httpx.Response(200, content=(FIXTURES / name).read_bytes())
        return httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_greenhouse_parses_escaped_html_and_filters_titles():
    with client_for({"greenhouse": "greenhouse.json"}) as c:
        [p] = ats.greenhouse(c, "JetBrains", "jetbrains")
    assert p.title == "Junior ML Engineer" and p.company == "JetBrains" and p.source_is_origin
    assert p.ats_job_id == "4932739101" and "Build LLM tools." in p.description and "- Python" in p.description


def test_ashby_skips_unlisted_and_merges_locations():
    with client_for({"ashbyhq": "ashby.json"}) as c:
        [p] = ats.ashby(c, "Higgsfield AI", "higgsfieldai")
    assert "Almaty, Kazakhstan" in p.location and "Remote" in p.location and p.remote


def test_workable_fetches_details_only_for_relevant_titles():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        name = "workable_detail.json" if "/v2/" in str(request.url) else "workable_list.json"
        return httpx.Response(200, content=(FIXTURES / name).read_bytes())

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        [p] = ats.workable(c, "ZeroAvia", "zeroavia")
    assert p.country == "DE" and "MSc in CS" in p.description
    assert sum("/v2/" in u for u in calls) == 1


def test_teamtailor_rss():
    with client_for({"teamtailor": "teamtailor.rss"}) as c:
        [p] = ats.teamtailor(c, "Sumsub", "sumsub")
    assert p.location == "Limassol, Cyprus" and p.remote and "fraud models" in p.description


def test_personio_years_become_a_sentence_the_seniority_rule_reads():
    with client_for({"personio": "personio.xml"}) as c:
        postings = ats.personio(c, "Personio", "personio")
    assert postings == []  # "Staff Software Engineer, Data Platform" — "Data Platform" is not in the target field
    from job_search.verify.seniority import required_years
    assert required_years("Required experience: 7-10 years.")[0] == 7


def test_arbeitsagentur_list_and_detail():
    with client_for({"jobdetails": "ba_detail.json", "/jobs": "ba_list.json"}) as c:
        [p] = boards.arbeitsagentur(c, ["Machine Learning"], 7, 1)
    assert p.country == "DE" and p.city == "Braunschweig" and not p.source_is_origin
    assert p.url.endswith("12362-TR249390_4973CS-S") and "ML Engineer" in p.description


def test_arbeitnow():
    with client_for({"arbeitnow": "arbeitnow.json"}) as c:
        [p] = boards.arbeitnow(c, 3)
    assert p.title == "Junior AI Engineer" and p.location == "Munich"


def test_himalayas_drops_senior_only_and_sets_regions():
    with client_for({"himalayas": "himalayas.json"}) as c:
        [p] = boards.himalayas(c, ["nlp"], ["Germany"], 1)
    assert p.remote and p.remote_regions == ["Germany"]


def test_remoteok_skips_legal_notice():
    with client_for({"remoteok": "remoteok.json"}) as c:
        [p] = boards.remoteok(c)
    assert p.title == "Associate Data Scientist" and p.remote_regions == ["Worldwide"]


def test_run_source_isolates_errors():
    def boom():
        raise httpx.ConnectError("down")
    result = run_source("x", boom)
    assert result.postings == [] and "ConnectError" in result.error


@pytest.mark.parametrize("title,expected", [
    ("Junior Machine Learning Engineer", True), ("KI-Entwickler (m/w/d)", True), ("Data Scientist", True),
    ("Graduate Software Engineer", True), ("NLP Engineer", True), ("Sales Manager DACH", False),
    ("Lagerhelfer (m/w/d)", False), ("Accounts Payable Specialist", False),
])
def test_title_relevance(title, expected):
    assert is_relevant_title(title) is expected


def test_html_to_text_blocks_and_entities():
    assert html_to_text("<p>A&amp;B</p><ul><li>x</li></ul>") == "A&B\n- x"


def test_html_to_text_handles_mixed_escaped_and_real_tags():
    # Arbeitnow (live run 2026-10-23): real tags around entity-escaped markup.
    raw = "<div>&lt;p&gt;Senior-level experience.&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Python&lt;/li&gt;&lt;/ul&gt;</div>"
    assert html_to_text(raw) == "Senior-level experience.\n- Python"


def test_jobspipe_paginates_respects_budget_and_marks_origin(monkeypatch):
    from job_search.sources import jobspipe
    import json as _json

    monkeypatch.setenv("JOBSPIPE_API_KEY", "test-key")
    bodies = []

    def handler(request):
        body = _json.loads(request.content)
        bodies.append(body)
        assert request.headers["Authorization"] == "Bearer test-key"
        name = "jobspipe_page2.json" if body.get("cursor") else "jobspipe_page1.json"
        return httpx.Response(200, content=(FIXTURES / name).read_bytes())

    monkeypatch.setattr(jobspipe.time, "sleep", lambda s: None)
    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        postings = jobspipe.fetch(c, [{"filters": {"job_country_code_or": ["DE"]}, "max_results": 10}], 10)
    assert [p.title for p in postings] == ["Junior Machine Learning Engineer", "AI Engineer"]  # closed job dropped
    assert postings[0].source_is_origin and not postings[1].source_is_origin
    assert postings[0].country == "DE" and postings[0].city == "Munich"
    assert bodies[0]["limit"] == 10 and bodies[1]["cursor"] == "abc" and bodies[1]["limit"] == 8


def test_jobspipe_daily_budget_caps_credits_spent(monkeypatch):
    """Credits = jobs returned. With full pages, two searches must stop at the daily budget."""
    import json as _json
    from job_search.sources import jobspipe
    monkeypatch.setenv("JOBSPIPE_API_KEY", "k")
    monkeypatch.setattr(jobspipe.time, "sleep", lambda s: None)
    returned = []

    def handler(request):
        limit = _json.loads(request.content)["limit"]
        jobs = [{"id": f"j{len(returned) + i}", "job_title": "ML Engineer", "url": f"https://x.io/jobs/{len(returned) + i}"}
                for i in range(limit)]
        returned.extend(jobs)
        return httpx.Response(200, json={"metadata": {"next_cursor": "more"}, "data": jobs})

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        jobspipe.fetch(c, [{"filters": {}, "max_results": 20}, {"filters": {}, "max_results": 20}], 25)
    assert len(returned) == 25


def test_jobspipe_without_key_is_reported_not_crashing(monkeypatch):
    from job_search.sources import jobspipe
    monkeypatch.delenv("JOBSPIPE_API_KEY", raising=False)
    result = run_source("jobspipe", lambda: jobspipe.fetch(None, [{"filters": {}}], 5))
    assert "JOBSPIPE_API_KEY not set" in result.error


def test_dropped_connection_is_retried(monkeypatch):
    # Live run 2026-10-25 08:01, right after wake: Bundesagentur "Server disconnected" killed the source.
    from job_search.sources import base
    monkeypatch.setattr(base.time, "sleep", lambda s: None)
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
        return httpx.Response(200, json={"ok": True})

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        assert base.get_with_retry(c, "https://example.com/api").json() == {"ok": True}
    assert len(calls) == 2

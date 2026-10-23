import httpx

from job_search.verify import liveness


def test_404_fails(posting):
    assert liveness.classify(posting(), 404, "", "").status == "fail"


def test_closed_message_fails(posting):
    v = liveness.classify(posting(), 200, posting().url, "<h1>This job is no longer accepting applications</h1>")
    assert v.status == "fail"


def test_german_closed_message_fails(posting):
    v = liveness.classify(posting(), 200, posting().url, "Diese Stelle ist nicht mehr verfügbar.")
    assert v.status == "fail"


def test_redirect_to_listing_fails(posting):
    p = posting(url="https://careers.acme.com/jobs/123456")
    assert liveness.classify(p, 200, "https://careers.acme.com/jobs", "Open positions").status == "fail"


def test_live_on_origin_passes(posting):
    p = posting()
    assert liveness.classify(p, 200, p.url, "Apply now").status == "pass"


def test_live_on_aggregator_only_is_flagged(posting):
    p = posting(url="https://www.englishjobs.de/job/123456", source_is_origin=False)
    assert liveness.classify(p, 200, p.url, "Apply now").status == "flag"


def test_forbidden_is_flagged(posting):
    assert liveness.classify(posting(), 403, "", "").status == "flag"


def test_ats_listing_today_passes_without_http(posting):
    p = posting(ats="greenhouse", ats_job_id="1234567")

    def boom(request):  # any network call would be a bug
        raise AssertionError("no HTTP expected")

    with httpx.Client(transport=httpx.MockTransport(boom)) as client:
        assert liveness.check(p, client).status == "pass"


def test_check_uses_client(posting):
    p = posting(url="https://careers.acme.com/jobs/987654")
    transport = httpx.MockTransport(lambda r: httpx.Response(410, text="gone"))
    with httpx.Client(transport=transport) as client:
        assert liveness.check(p, client).status == "fail"


def test_blocked_check_on_connector_posting_says_live_on_that_board(posting):
    # Indeed answers 403 to automated checks, but the connector returned the posting as live today.
    p = posting(url="https://to.indeed.com/aa8lf6m7qsq8", source="connector:indeed", source_is_origin=False)
    v = liveness.classify(p, 403, "", "")
    assert v.status == "flag"
    assert v.reason == "Live on Indeed today; employer page not checked"


def test_blocked_check_on_plain_aggregator_still_asks_for_manual_check(posting):
    p = posting(url="https://www.arbeitnow.com/jobs/x/123456", source="arbeitnow", source_is_origin=False)
    assert liveness.classify(p, 403, "", "").reason == "Could not open the posting page (HTTP 403) — check it manually"


def test_aggregator_only_wording_names_the_board(posting):
    p = posting(url="https://www.arbeitnow.com/jobs/x/123456", source="arbeitnow", source_is_origin=False)
    assert liveness.classify(p, 200, p.url, "Apply").reason == (
        "Confirmed live on Arbeitnow, not on the employer's own site — check the company site before applying")

from job_search.dedup import check_duplicate, fingerprint, normalize_url, urls_in_reports


def test_normalize_url_strips_tracking_and_trailing_slash():
    a = "https://www.Boards.greenhouse.io/acme/jobs/123/?gh_src=abc&utm_source=linkedin#apply"
    assert normalize_url(a) == "https://boards.greenhouse.io/acme/jobs/123"


def test_normalize_url_keeps_meaningful_params():
    assert normalize_url("https://acme.com/job?id=5&utm_medium=x") == "https://acme.com/job?id=5"


def test_fingerprint_ignores_gender_tags_and_legal_suffix():
    assert fingerprint("Acme GmbH", "Junior Data Scientist (m/w/d)") == fingerprint("ACME", "junior data scientist (f/m/x)")


def test_urls_in_reports(tmp_path):
    (tmp_path / "job-search_daily-reports_2026-10-20.md").write_text(
        "1. [Junior ML](https://jobs.lever.co/acme/abc-123?lever-source=x) — Acme\n"
        "2. <https://boards.greenhouse.io/b/jobs/99>.\n"
    )
    (tmp_path / "other.md").write_text("https://ignored.example.com/jobs/1")
    assert urls_in_reports(tmp_path) == {
        "https://jobs.lever.co/acme/abc-123",
        "https://boards.greenhouse.io/b/jobs/99",
    }


def test_reported_url_is_duplicate(posting):
    p = posting(url="https://boards.greenhouse.io/acme/jobs/1234567?utm_source=x")
    assert check_duplicate(p, {"https://boards.greenhouse.io/acme/jobs/1234567"}, {}).status == "fail"


def test_repost_at_new_url_is_duplicate(posting):
    p = posting(url="https://boards.greenhouse.io/acme/jobs/7654321")
    fps = {fingerprint(p.company, p.title): False}
    assert check_duplicate(p, set(), fps).status == "fail"


def test_reopened_role_is_flagged_not_failed(posting):
    p = posting(url="https://boards.greenhouse.io/acme/jobs/7654321")
    fps = {fingerprint(p.company, p.title): True}
    assert check_duplicate(p, set(), fps).status == "flag"


def test_new_posting_passes(posting):
    assert check_duplicate(posting(), set(), {}).status == "pass"


def test_collapse_same_day_duplicates_prefers_origin_then_longer_text(posting):
    from job_search.dedup import collapse_duplicates

    aggregator = posting(url="https://himalayas.app/companies/acme/jobs/ml", source_is_origin=False,
                         description="x" * 5000)
    origin_short = posting(url="https://boards.greenhouse.io/acme/jobs/1", description="short")
    origin_long = posting(url="https://boards.greenhouse.io/acme/jobs/2", description="longer text")
    other = posting(title="Junior Data Scientist", url="https://boards.greenhouse.io/acme/jobs/3")
    kept, dropped = collapse_duplicates([aggregator, origin_short, origin_long, other])
    assert [p.url for p in kept] == [origin_long.url, other.url]
    assert len(dropped) == 2


def test_urls_in_reports_ignores_the_current_and_later_days(tmp_path):
    from datetime import date
    (tmp_path / "job-search_daily-reports_2026-10-22.md").write_text("https://a.example.com/jobs/1111")
    (tmp_path / "job-search_daily-reports_2026-10-23.md").write_text("https://b.example.com/jobs/2222")
    assert urls_in_reports(tmp_path, before=date(2026, 10, 23)) == {"https://a.example.com/jobs/1111"}

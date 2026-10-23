from datetime import date

from job_search import report
from job_search.dedup import normalize_url, urls_in_reports
from job_search.models import Verdict
from tests.test_scoring import result


def render(entries, audit=None):
    funnel = report.Funnel(100, 90, 20, 15, len(entries))
    return report.render(date(2026, 10, 23), entries, 10, 0.3, None, "Uncalibrated.", funnel,
                         audit or {}, [])


def test_report_lists_postings_and_says_when_fewer_than_ten(posting):
    entry = report.Entry(posting(), 81.2, result(), [Verdict.flag("seniority", "seniority not stated")])
    text = render([entry])
    assert "[Junior Machine Learning Engineer](https://boards.greenhouse.io/acme/jobs/1234567) — 81" in text
    assert "fewer than 10" in text and "⚠ seniority not stated" in text and "log-outcome" in text


def test_only_reported_urls_appear_so_tomorrows_dedup_is_exact(posting, tmp_path):
    entry = report.Entry(posting(), 80, result())
    audit = {"enrollment": ["Werkstudent Data — Foo GmbH"], "link": ["Some role — Bar"]}
    report.write(tmp_path, date(2026, 10, 23), render([entry], audit))
    assert urls_in_reports(tmp_path) == {normalize_url(posting().url)}


def test_empty_day(posting):
    assert "No new postings passed every filter today." in render([])


def test_markdown_to_html_covers_the_report_format(posting):
    entry = report.Entry(posting(), 81.2, result(), [Verdict.flag("seniority", "seniority not stated")])
    html = report.to_html(render([entry], {"enrollment": ["Werkstudent <Data> — Foo"]}))
    assert '<a href="https://boards.greenhouse.io/acme/jobs/1234567">Junior Machine Learning Engineer</a>' in html
    assert "<h1>Job digest 2026-10-23</h1>" in html and "<strong>Chance today: 30/100</strong>" in html
    assert "<li>⚠ seniority not stated</li>" in html and "<code>abc" not in html
    assert "<table" in html and "<td>Student, intern or thesis role</td>" in html
    assert "Werkstudent &lt;Data&gt;" in html  # text is escaped


def test_plain_text_has_no_markdown_syntax(posting):
    text = report.to_plain_text(render([report.Entry(posting(), 80, result())]))
    assert "## " not in text and "**" not in text and "](" not in text
    assert "Junior Machine Learning Engineer — https://boards.greenhouse.io/acme/jobs/1234567" in text


def test_report_uses_plain_source_names_short_ids_and_plain_rule_labels(posting):
    p = posting(source="connector:indeed", url="https://to.indeed.com/aa8lf6m7qsq8")
    text = render([report.Entry(p, 80, result())], {"description_language": ["X — Y"], "llm_crosscheck": ["A — B"]})
    assert "· via Indeed" in text and "connector:indeed" not in text
    assert f"ID `{p.id}`" in text and text.count("log-outcome") == 1  # once, in the footer
    assert "| Not written in English or Russian | 1 |" in text and "| Failed the fact check against the posting | 1 |" in text


def test_source_labels():
    from job_search.models import source_label
    assert source_label("connector:jobdatalake") == "JobDataLake"
    assert source_label("jobspipe:linkedin") == "LinkedIn (via JobsPipe)"
    assert source_label("greenhouse") == "Greenhouse (company job board)"
    assert source_label("something-new") == "something-new"

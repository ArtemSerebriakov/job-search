import pytest

from job_search.verify import link


@pytest.mark.parametrize("url", [
    "https://boards.greenhouse.io/qdrant/jobs/4567890",
    "https://jobs.lever.co/revolut/3f1c2a7e-1234-4cde-9abc-1234567890ab",
    "https://jobs.ashbyhq.com/nebius/9b0d1c2e-aaaa-bbbb-cccc-1234567890ab",
    "https://www.linkedin.com/jobs/view/4012345678",
    "https://www.jetbrains.com/careers/jobs/junior-ml-engineer-2345/",
    "https://www.arbeitsagentur.de/jobsuche/jobdetail/10001-1234567890-S",
])
def test_posting_urls_pass(posting, url):
    assert link.check(posting(url=url)).status == "pass"


@pytest.mark.parametrize("url", [
    "",
    "https://www.google.com/search?q=junior+ml+engineer+munich",
    "https://www.linkedin.com/jobs/search/?keywords=machine%20learning",
    "https://de.indeed.com/jobs?q=data+scientist&l=M%C3%BCnchen",
    "https://www.jetbrains.com/careers/jobs/",
    "https://careers.example.com/en/careers",
    "https://techcrunch.com/news/2026/10/01/startup-hiring/",
    "ftp://example.com/job",
])
def test_non_posting_urls_fail(posting, url):
    assert link.check(posting(url=url)).status == "fail"

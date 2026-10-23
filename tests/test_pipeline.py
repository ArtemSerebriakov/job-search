from job_search.dedup import normalize_url
from job_search.verify.pipeline import verify


def test_good_posting_passes_all_static_rules(posting, criteria):
    result = verify(posting(), criteria, set(), {})
    assert result.passed, result.failures


def test_pipeline_stops_at_first_failure(posting, criteria):
    result = verify(posting(title="Werkstudent Data Science (m/w/d)"), criteria, set(), {})
    assert not result.passed
    assert [v.rule for v in result.failures] == ["enrollment"]
    assert result.verdicts[-1].rule == "enrollment"


def test_duplicate_skips_other_rules(posting, criteria):
    p = posting()
    result = verify(p, criteria, {normalize_url(p.url)}, {})
    assert [v.rule for v in result.verdicts] == ["dedup"]

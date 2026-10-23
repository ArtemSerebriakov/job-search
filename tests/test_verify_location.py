import pytest

from job_search.verify import location


@pytest.mark.parametrize("loc,country", [
    ("München, Bayern", None), ("Berlin", None), ("Amsterdam, Netherlands", None),
    ("Dubai, UAE", None), ("Hybrid", "DE"), ("Bielefeld", None),
])
def test_allowed_countries_pass(posting, criteria, loc, country):
    p = posting(company="Some Startup GmbH", location=loc, country=country)
    assert location.check(p, criteria).status == "pass"


@pytest.mark.parametrize("loc", ["London, United Kingdom", "Warsaw, Poland", "Lisbon", "Remote - US", "Lausanne", "Basel"])
def test_other_countries_fail_for_unnamed_companies(posting, criteria, loc):
    p = posting(company="Some Startup", location=loc, country=None, remote="Remote" in loc)
    assert location.check(p, criteria).status == "fail"


@pytest.mark.parametrize("company,loc", [
    ("JetBrains", "Amsterdam, Netherlands"),
    ("JetBrains", "Limassol, Cyprus"),
    ("Kaspi.kz", "Almaty, Kazakhstan"),
    ("Uzum", "Tashkent, Uzbekistan"),
    ("Revolut Ltd", "London, United Kingdom"),
    ("EPAM Systems, Inc.", "Remote, Poland"),
    ("Constructor.io", "Remote"),
    ("Yango Group", "Dubai"),
])
def test_named_companies_pass_anywhere(posting, criteria, company, loc):
    p = posting(company=company, location=loc, country=None)
    assert location.check(p, criteria).status == "pass"


def test_named_company_matching_is_not_substring(criteria):
    assert criteria.match_named_company("Flo Health") == "Flo Health"
    assert criteria.match_named_company("Florida Software") is None
    assert criteria.match_named_company("Salmonella Labs") is None
    assert criteria.match_named_company("Andersen Tax") is None


def test_remote_open_to_germany_passes(posting, criteria):
    p = posting(company="X", location="Remote", country=None, remote=True, remote_regions=["DE"])
    assert location.check(p, criteria).status == "pass"


def test_remote_emea_is_flagged(posting, criteria):
    p = posting(company="X", location="Remote", country=None, remote=True, remote_regions=["EMEA"])
    assert location.check(p, criteria).status == "flag"


def test_unrecognised_town_is_flagged_not_failed(posting, criteria):
    p = posting(company="X", location="Walldorf", country=None)
    assert location.check(p, criteria).status == "flag"


def test_location_bonus_prefers_munich(posting, criteria):
    munich = posting(location="Garching bei München")
    berlin = posting(location="Berlin")
    dubai = posting(location="Dubai", country="AE")
    assert location.location_bonus(munich, criteria) > location.location_bonus(berlin, criteria) \
        > location.location_bonus(dubai, criteria)

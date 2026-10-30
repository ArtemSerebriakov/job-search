import pytest

from job_search.verify import language


@pytest.mark.parametrize("body", [
    "Fließende Deutsch- und Englischkenntnisse.",
    "Sehr gute Deutschkenntnisse in Wort und Schrift.",
    "Verhandlungssicheres Deutsch und gutes Englisch.",
    "Fluent German and English are required.",
    "German (C1) and English (B2).",
    "You are fluent in English and German.",
    "Deutsch fließend, Englisch gut.",
    "Business-fluent German is a must.",
    "Excellent German language skills.",
    "Fluent Dutch and English.",
    "German at C1 level.",
])
def test_german_fluency_fails(posting, body):
    assert language.check(posting(description=body)).status == "fail"


@pytest.mark.parametrize("body", [
    "Fluent English. German is a plus.",
    "Excellent English; basic German is nice to have.",
    "Professional experience with German automotive OEMs.",
    "Deutschkenntnisse sind von Vorteil.",
    "English C1 is required.",
    "We work with strong German and international clients.",
])
def test_no_german_requirement_passes(posting, body):
    assert language.check(posting(description=body)).status == "pass"


def test_german_required_but_english_working_language_passes(posting):
    body = "Our working language is English. Fluent German is required for customer calls."
    assert language.check(posting(description=body)).status == "pass"



@pytest.mark.parametrize("body", [
    "Upper-intermediate German or higher.",
    "Advanced German is required.",
    "German: upper intermediate (B2).",
])
def test_upper_intermediate_or_advanced_german_fails(posting, body):
    assert language.check(posting(description=body)).status == "fail"


@pytest.mark.parametrize("body", [
    # Andersen "ML Engineer (with German language)", 2026-10-30
    "Level of German – from Intermediate+ and above.",
    "Intermediate German.",
    "German B1 or higher.",
    "Very good English skills, German B1 or higher.",  # was "passes" until 2026-10-30; B1 is above beginner
    "Conversational German.",
])
def test_intermediate_german_requirement_is_flagged(posting, body):
    assert language.check(posting(description=body)).status == "flag"


@pytest.mark.parametrize("body", [
    "Intermediate German is a plus.",
    "Basic German is nice to have.",
    "Intermediate Python skills.",
])
def test_optional_or_unrelated_intermediate_passes(posting, body):
    assert language.check(posting(description=body)).status == "pass"

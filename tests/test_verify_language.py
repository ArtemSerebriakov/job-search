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
    "Very good English skills, German B1 or higher.",
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


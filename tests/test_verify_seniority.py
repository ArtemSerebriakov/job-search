import pytest

from job_search.verify import seniority
from job_search.verify.seniority import required_years


@pytest.mark.parametrize("title", [
    "Senior Machine Learning Engineer",
    "Sr. Data Scientist",
    "Lead AI Engineer",
    "Staff Applied Scientist",
    "Principal Research Scientist",
    "Head of Data Science",
    "Machine Learning Engineering Manager",
    "Data Scientist II",
    "Mid-Level NLP Engineer",
    "Teamleiter Data Science (m/w/d)",
    "Associate Director, AI",
    "Solutions Architect GenAI",
    # found in the first live run (2026-10-23)
    "Leitung KI & industrielle Digitalisierung (m/w/d)",
    "Gruppenleitung AI, Machine Learning & MLOps",
    "Middle AI Platform Engineer (Python, Go, Cloud)",
    "Technical Co-Founder (AI Efficiency) @ AI Venture",
    "CTO (m/w/d) KI-Startup",
])
def test_senior_titles_fail(posting, title):
    assert seniority.check(posting(title=title)).status == "fail"


@pytest.mark.parametrize("body,expected", [
    ("You have 3+ years of experience in machine learning.", 3),
    ("At least 3 years of professional experience with Python.", 3),
    ("Minimum of 4 years experience building ML systems.", 4),
    ("2-4 years of experience in NLP.", 2),
    ("1–2 years experience in data science.", 1),
    ("Mindestens 3 Jahre Berufserfahrung im Bereich Data Science.", 3),
    ("Berufserfahrung von mindestens 5 Jahren", 5),
    ("Mehrere Jahre Berufserfahrung in der Softwareentwicklung.", 3),
    ("Mehrjährige Berufserfahrung im Bereich Machine Learning.", 3),
    ("Sie verfügen über langjährige Erfahrung in der Softwareentwicklung.", 3),
    ("You bring several years of experience in ML.", 3),
    ("Three years of experience with PyTorch.", 3),
    ("Experience of 5+ years in a similar role.", 5),
    ("Master's degree and 1 year of experience, or Bachelor's degree and 3 years of experience.", 1),
    ("0-2 years of experience in machine learning.", 0),
    # Andersen "AI Developer (Germany)", 2026-10-30: abbreviation periods and a long gap.
    ("Experience with LLMs (e.g. GPT-4, Mistral, LLaMA) for 3+ years.", 3),
    ("Experience with cloud platforms, i.e. Azure or AWS, for at least 4 years.", 4),
    ("Berufserfahrung mit ML-Systemen, z.B. Empfehlungssysteme, von mindestens 3 Jahren.", 3),
    ("Ca. 3 Jahre Berufserfahrung im Bereich Data Science.", 3),
])
def test_required_years(body, expected):
    years, _ = required_years(body)
    assert years == expected


@pytest.mark.parametrize("body", [
    "We were founded 10 years ago and serve 3 million users.",
    "30 days of vacation and a yearly education budget.",
    "5+ years of experience with Kubernetes is a plus.",
    "Experience with LLMs, Python and SQL.",
    "Wir sind seit 20 Jahren am Markt.",
    "Experience with many tools (e.g. Docker, Kubernetes, Terraform, Airflow and dbt), which we have used for 10 years.",
    "Entwicklung einer mehrjährigen Roadmap für KI.",  # live run 2026-10-23: not an experience requirement
])
def test_no_requirement_found(body):
    years, _ = required_years(body)
    assert years is None


def test_junior_title_with_3_years_in_body_fails(posting):
    # "Junior" in the title must not override the body requirement.
    p = posting(title="Junior Data Scientist", description="Requirements: 3+ years of experience in ML.")
    assert seniority.check(p).status == "fail"


def test_nice_to_have_years_do_not_fail(posting):
    p = posting(title="Junior ML Engineer",
                description="1+ year of experience with Python.\n5+ years of experience in ML is a plus.")
    assert seniority.check(p).status == "pass"


def test_max_of_requirements_across_sentences(posting):
    p = posting(title="ML Engineer",
                description="1+ year with Docker.\nYou have 4+ years of experience in machine learning.")
    assert seniority.check(p).status == "fail"


@pytest.mark.parametrize("title", [
    "Graduate AI Engineer", "Junior NLP Engineer", "Associate Data Scientist",
    "Machine Learning Engineer I", "New Grad Software Engineer, ML", "Berufseinsteiger Data Science (m/w/d)",
])
def test_entry_titles_pass(posting, title):
    assert seniority.check(posting(title=title, description="Build LLM tools.")).status == "pass"


def test_unstated_seniority_is_flagged(posting):
    p = posting(title="Machine Learning Engineer", description="Build LLM agents with LangGraph.")
    assert seniority.check(p).status == "flag"


def test_associate_in_consulting_without_years_fails(posting):
    p = posting(title="Associate, AI & Data", company="McKinsey & Company",
                description="Join our consulting teams advising clients on AI strategy.")
    assert seniority.check(p).status == "fail"


def test_associate_in_consulting_with_low_years_passes(posting):
    p = posting(title="Associate Consultant Data Science", company="Big Four Advisory",
                description="0-2 years of experience in data science; consulting interest.")
    assert seniority.check(p).status == "pass"


def test_associate_in_tech_passes(posting):
    p = posting(title="Associate Machine Learning Engineer", company="Nebius",
                description="Train and deploy LLMs.")
    assert seniority.check(p).status == "pass"


@pytest.mark.parametrize("body", [
    # Scout24 "AI Automation Engineer", live run 2026-10-23
    "Senior-level software engineering experience, with strong system-design skills.",
    "You bring senior level experience in machine learning.",
    "Proven experience as a senior engineer.",
    "Berufserfahrung auf Senior-Level im Bereich Data Science.",
])
def test_senior_experience_requirement_in_body_fails(posting, body):
    p = posting(title="AI Automation Engineer (d/m/f)", description=body)
    assert seniority.check(p).status == "fail"


@pytest.mark.parametrize("body", [
    "You will learn from senior engineers in a supportive team.",
    "Senior-level experience is a plus.",
    "Our seniors mentor every new joiner.",
])
def test_senior_mentions_that_are_not_requirements_pass(posting, body):
    p = posting(title="Junior AI Engineer", description=body)
    assert seniority.check(p).status == "pass"

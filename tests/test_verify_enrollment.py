import pytest

from job_search.verify import enrollment

# Titles that leaked into the reference digest (screenshot, 2026-09-29) plus common variants.
LEAKED_TITLES = [
    "Praktikant Business Building & AI Automation (m/w/d) – Digital Education mit Impact",
    "Werkstudent*in Data Analytics (m/w/d)",
    "Werkstudent (m/w/d) MarTech, Data & Analytics",
    "Internship AI & Automation - Energy (m/f/d)",
    "Werkstudent:in Vertriebsreporting (w/m/d) am Standort in Berlin",
    "Praktikant/Werkstudent „Forschung & Innovation – Datengetriebene Entwicklung autonomer Systeme“ (m/w/d)",
    "Working Student Modeled Data",
    "Intern AI & Data Engineering (m/f/d)",
    "Masterarbeit: LLM-basierte Diagnose",
    "Master Thesis – Retrieval Augmented Generation",
    "Studentische Hilfskraft Machine Learning",
    "Duales Studium Data Science (B.Sc.)",
    "Pflichtpraktikum Data Science",
    "ML Engineering Intern, Summer 2027",
]


@pytest.mark.parametrize("title", LEAKED_TITLES)
def test_student_titles_fail(posting, title):
    assert enrollment.check(posting(title=title)).status == "fail"


@pytest.mark.parametrize("body", [
    "You are currently enrolled in a Master's program in Computer Science.",
    "Du bist an einer Hochschule immatrikuliert.",
    "Voraussetzung: laufendes Studium der Informatik.",
    "You are currently pursuing a Master's degree in Data Science.",
    "Please attach your enrollment certificate.",
    "You are a student in a STEM field.",
])
def test_enrollment_requirement_in_body_fails(posting, body):
    assert enrollment.check(posting(description=body)).status == "fail"


@pytest.mark.parametrize("title,body", [
    ("Graduate AI Engineer", "Completed Master's degree in Computer Science or related field."),
    ("Junior Data Scientist", "Abgeschlossenes Studium der Informatik, Mathematik oder vergleichbar."),
    ("AI Engineer", "All employees are enrolled in our pension plan from day one."),
    ("Associate Applied Scientist", "You recently graduated and want to grow with us."),
    ("Junior NLP Engineer", "You will mentor our working students."),
])
def test_graduate_roles_pass(posting, title, body):
    assert enrollment.check(posting(title=title, description=body)).status == "pass"

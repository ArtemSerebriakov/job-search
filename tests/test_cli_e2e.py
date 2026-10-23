"""Two-day end-to-end run of the CLI with fake sources, a fake embedder and hand-written scores."""

import json
from datetime import date

import numpy as np
import pytest

from job_search import cli
from tests.conftest import make_posting

DAY1, DAY2 = date(2026, 10, 23), date(2026, 10, 24)
ENGLISH = ("We are looking for a graduate engineer to join our team. You will build LLM agents with Python and "
           "PyTorch, and you will work with our research team on retrieval. What you bring: a Master's degree "
           "and curiosity. What we offer: mentorship and a hybrid setup in our office.")


def fake_embed(texts, **_):
    return np.array([[1.0, len(t) % 7, t.count("LLM")] for t in texts])


GOOD = [make_posting(url=f"https://boards.greenhouse.io/acme/jobs/10000{i}", title=f"Graduate AI Engineer {i}",
                     ats="greenhouse", ats_job_id=str(i), description=ENGLISH) for i in range(3)]
BAD = [
    make_posting(url="https://boards.greenhouse.io/acme/jobs/200001", title="Werkstudent Data Science (m/w/d)",
                 ats="greenhouse", ats_job_id="w", description=ENGLISH),
    make_posting(url="https://boards.greenhouse.io/acme/jobs/200002", title="Senior ML Engineer",
                 ats="greenhouse", ats_job_id="s", description=ENGLISH),
    make_posting(url="https://boards.greenhouse.io/other/jobs/200003", title="Junior ML Engineer", company="Other Co",
                 location="London, United Kingdom", country=None, ats="greenhouse", ats_job_id="l", description=ENGLISH),
]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(cli, "reports_dir", lambda: tmp_path / "reports")
    monkeypatch.setattr(cli, "get_embedder", lambda name: fake_embed)
    return tmp_path


def run_day(day, postings, monkeypatch, scores_for=None):
    monkeypatch.setattr(cli, "get_sources", lambda client: [("fake", lambda: postings)])
    d = day.isoformat()
    assert cli.main(["collect", "--date", d]) == 0
    assert cli.main(["prepare", "--date", d, "--no-liveness"]) == 0
    batch = cli.batch_dir(day)
    to_score = json.loads((batch / "to_score.json").read_text())
    scores = [{"posting_id": x["posting_id"],
               "sub_scores": {"genai_relevance": 90, "skills_match": 80, "seniority_fit": 85, "domain_fit": 60, "growth": 70},
               "facts": {"min_years": None, "requires_enrollment": False, "german_level": "none",
                         "english_working_language": True},
               "evidence": {}, "rationale": "LLM agents."} for x in to_score]
    (batch / "scores.json").write_text(json.dumps(scores_for(scores) if scores_for else scores))
    return to_score


def test_two_day_run(env, monkeypatch):
    to_score = run_day(DAY1, GOOD + BAD, monkeypatch)
    assert {x["title"] for x in to_score} == {p.title for p in GOOD}
    assert cli.main(["finalize", "--date", DAY1.isoformat()]) == 0

    report1 = (env / "reports" / "job-search_daily-reports_2026-10-23.md").read_text()
    for p in GOOD:
        assert p.url in report1
    for p in BAD:
        assert p.url not in report1
    assert "fewer than 10" in report1 and "| Student, intern or thesis role | 1 |" in report1

    # Day 2: the same postings are still listed plus one new one; only the new one may be reported.
    new = make_posting(url="https://boards.greenhouse.io/acme/jobs/300001", title="Junior NLP Engineer",
                       ats="greenhouse", ats_job_id="n", description=ENGLISH)
    run_day(DAY2, GOOD + BAD + [new], monkeypatch)
    assert cli.main(["finalize", "--date", DAY2.isoformat()]) == 0
    report2 = (env / "reports" / "job-search_daily-reports_2026-10-24.md").read_text()
    assert new.url in report2
    assert not any(p.url in report2 for p in GOOD)


def test_finalize_refuses_invalid_scores_unless_partial(env, monkeypatch):
    run_day(DAY1, GOOD, monkeypatch, scores_for=lambda s: s[:-1])  # one posting left unscored
    assert cli.main(["finalize", "--date", DAY1.isoformat()]) == cli.EXIT_SCORING_PROBLEMS
    assert cli.main(["finalize", "--date", DAY1.isoformat(), "--allow-partial"]) == 0
    text = (env / "reports" / "job-search_daily-reports_2026-10-23.md").read_text()
    assert "## Scoring problems" in text and "missing" in text


def test_log_outcome(env, monkeypatch):
    run_day(DAY1, GOOD, monkeypatch)
    cli.main(["finalize", "--date", DAY1.isoformat()])
    assert cli.main(["log-outcome", GOOD[0].id, "--status", "sent", "--date", DAY1.isoformat()]) == 0
    assert cli.main(["log-outcome", "nope", "--status", "sent"]) == 1


def test_rerunning_finalize_replaces_the_days_reported_set(env, monkeypatch):
    run_day(DAY1, GOOD, monkeypatch)
    cli.main(["finalize", "--date", DAY1.isoformat()])
    batch = cli.batch_dir(DAY1)
    scores = json.loads((batch / "scores.json").read_text())
    for s in scores[1:]:
        s["sub_scores"] = {k: 0 for k in s["sub_scores"]}  # now below the threshold
    (batch / "scores.json").write_text(json.dumps(scores))
    cli.main(["finalize", "--date", DAY1.isoformat()])
    assert len(cli.open_db().reported_on(DAY1)) == 1

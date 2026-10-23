import json

import pytest

from job_search import scoring
from job_search.scoring import ScoreResult


def result(pid="abc", **facts):
    return ScoreResult.model_validate({
        "posting_id": pid,
        "sub_scores": {"genai_relevance": 90, "skills_match": 80, "seniority_fit": 70, "domain_fit": 60, "growth": 50},
        "facts": {"min_years": None, "requires_enrollment": False, "german_level": "none",
                  "english_working_language": True, **facts.pop("facts", {})},
        "evidence": facts.pop("evidence", {}),
        "rationale": "Strong LLM focus.",
    })


def test_load_and_validate_reports_invalid_missing_unknown_and_duplicates(tmp_path):
    good = result("a").model_dump()
    bad = {**result("b").model_dump(), "sub_scores": {"genai_relevance": 140}}
    path = tmp_path / "scores.json"
    path.write_text(json.dumps([good, bad, result("zzz").model_dump(), good]))
    valid, problems = scoring.load_and_validate(path, {"a", "b", "c"})
    assert set(valid) == {"a"}
    text = "\n".join(problems)
    assert "b: invalid" in text and "c: missing" in text and "zzz: not in to_score.json" in text and "a: scored twice" in text


def test_load_and_validate_missing_file(tmp_path):
    valid, problems = scoring.load_and_validate(tmp_path / "nope.json", {"a"})
    assert valid == {} and "does not exist" in problems[0]


def test_final_score_weights_and_bonus(criteria):
    r = result()
    expected = 90 * .30 + 80 * .25 + 70 * .20 + 60 * .15 + 50 * .10
    assert scoring.final_score(r, 0, criteria) == pytest.approx(expected, abs=0.1)
    assert scoring.final_score(r, 6, criteria) == pytest.approx(expected + 6, abs=0.1)


def test_cross_check_excludes_when_quote_is_verbatim(posting, criteria):
    p = posting(description="Requirements: at least 4 years of industry experience in ML.")
    r = result(facts={"min_years": 4}, evidence={"min_years": "at least 4 years of industry experience"})
    verdicts = scoring.cross_check(r, p, criteria)
    assert [v.status for v in verdicts] == ["fail"]


def test_cross_check_only_flags_when_quote_not_in_text(posting, criteria):
    p = posting(description="Build LLM agents.")
    r = result(facts={"min_years": 5}, evidence={"min_years": "5+ years of experience"})
    assert [v.status for v in scoring.cross_check(r, p, criteria)] == ["flag"]


def test_cross_check_german_respects_english_working_language(posting, criteria):
    p = posting(description="German C1 required. Our working language is English.")
    ok = result(facts={"german_level": "C1", "english_working_language": True}, evidence={"german_level": "German C1 required"})
    bad = result(facts={"german_level": "C1", "english_working_language": False}, evidence={"german_level": "German C1 required"})
    assert scoring.cross_check(ok, p, criteria) == []
    assert [v.status for v in scoring.cross_check(bad, p, criteria)] == ["fail"]


def test_facts_never_change_sub_scores(posting, criteria):
    clean = result()
    flagged = result(facts={"min_years": 5, "requires_enrollment": True})
    assert scoring.final_score(clean, 0, criteria) == scoring.final_score(flagged, 0, criteria)

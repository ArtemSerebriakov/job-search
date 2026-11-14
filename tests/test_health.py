import json
from datetime import date

import pytest

from job_search import health

DAY = date(2026, 10, 25)


def setup_day(tmp_path, *, log="=== start\n=== daily digest end (exit 0)\n", collect=None, discovered=True,
              scores=True, report_urls=("https://jobs.example.com/jobs/1001",), email_sent=True):
    data, reports, logs = tmp_path / "data", tmp_path / "reports", tmp_path / "logs"
    batch = data / "batches" / DAY.isoformat()
    for d in (batch, reports, logs):
        d.mkdir(parents=True, exist_ok=True)
    if log is not None:
        (logs / f"{DAY.isoformat()}.log").write_text(log)
    (batch / "collect.json").write_text(json.dumps(collect or {"greenhouse:x": {"relevant": 5, "new": 2, "error": None}}))
    if discovered:
        (batch / "discovered.json").write_text("[]")
        (batch / "discovered_connectors.json").write_text('[{"url": "u"}]')
        (batch / "discovered_browser_revolut.json").write_text('[{"url": "r"}, {"url": "s"}]')
    (batch / "to_score.json").write_text(json.dumps([{"posting_id": "a"}]))
    (batch / "prepare.json").write_text("{}")
    if scores:
        (batch / "scores.json").write_text(json.dumps([{
            "posting_id": "a",
            "sub_scores": {"genai_relevance": 1, "skills_match": 1, "seniority_fit": 1, "domain_fit": 1, "growth": 1},
            "facts": {}, "evidence": {}, "rationale": ""}]))
    if report_urls is not None:
        (reports / f"job-search_daily-reports_{DAY.isoformat()}.md").write_text(
            "\n".join(f"## 1. [Role]({u}) — 70" for u in report_urls))
    if email_sent:
        (batch / "email_sent.json").write_text('{"message_id": "m1"}')
    return health.Paths(data_dir=data, reports_dir=reports, logs_dir=logs)


def statuses(checks):
    return {c.name: c.status for c in checks}


LAUNCHD_OK = "state = not running\nruns = 3\nlast exit code = 0\n"


def test_healthy_day_passes_everything(tmp_path):
    checks = health.run_checks(DAY, setup_day(tmp_path), recipient="me@example.com", launchd_output=LAUNCHD_OK)
    assert set(statuses(checks).values()) == {"ok"}, checks
    assert health.exit_code(checks) == 0


def test_todays_failure_mode_is_caught(tmp_path):
    # 2026-10-24: launchd started the job, macOS blocked it, nothing else happened.
    paths = setup_day(tmp_path, log=None, discovered=False, scores=False, report_urls=None, email_sent=False)
    (paths.logs_dir / "launchd.err.log").write_text("/bin/bash: .../daily.sh: Operation not permitted\n")
    checks = health.run_checks(DAY, paths, recipient="me@example.com",
                               launchd_output="state = not running\nruns = 1\nlast exit code = 126\n")
    s = statuses(checks)
    assert s["launchd"] == "fail" and s["run log"] == "fail" and s["report"] == "fail" and s["email"] == "fail"
    assert any("Operation not permitted" in c.detail for c in checks)
    assert health.exit_code(checks) == 1


def test_error_lines_in_run_log_fail(tmp_path):
    paths = setup_day(tmp_path, log="=== start\nError: not logged in\n=== daily digest end (exit 1)\n")
    s = statuses(health.run_checks(DAY, paths, recipient="x@y.z", launchd_output=LAUNCHD_OK))
    assert s["run log"] == "fail"


def test_source_errors_warn_and_all_sources_down_fails(tmp_path):
    some = {"a": {"relevant": 3, "new": 1, "error": None}, "jobspipe": {"relevant": 0, "new": 0, "error": "HTTPStatusError: 402"}}
    s = statuses(health.run_checks(DAY, setup_day(tmp_path, collect=some), recipient="x@y.z", launchd_output=LAUNCHD_OK))
    assert s["sources"] == "warn"
    down = {"a": {"relevant": 0, "new": 0, "error": "ConnectError"}}
    s = statuses(health.run_checks(DAY, setup_day(tmp_path / "2", collect=down), recipient="x@y.z", launchd_output=LAUNCHD_OK))
    assert s["sources"] == "fail"


def test_repeated_url_from_earlier_report_fails(tmp_path):
    paths = setup_day(tmp_path)
    (paths.reports_dir / "job-search_daily-reports_2026-10-23.md").write_text("[Old](https://jobs.example.com/jobs/1001)")
    s = statuses(health.run_checks(DAY, paths, recipient="x@y.z", launchd_output=LAUNCHD_OK))
    assert s["dedup"] == "fail"


def test_missing_recipient_and_unloaded_job_fail(tmp_path):
    s = statuses(health.run_checks(DAY, setup_day(tmp_path), recipient=None, launchd_output=None))
    assert s["recipient"] == "fail" and s["launchd"] == "fail"


def test_running_job_is_ok(tmp_path):
    s = statuses(health.run_checks(DAY, setup_day(tmp_path), recipient="x@y.z",
                                   launchd_output="state = running\nruns = 4\nlast exit code = 0\n"))
    assert s["launchd"] == "ok"


def test_missing_browser_discovery_only_warns(tmp_path):
    paths = setup_day(tmp_path)
    (paths.batch(DAY) / "discovered_browser_revolut.json").unlink()
    checks = health.run_checks(DAY, paths, recipient="x@y.z", launchd_output=LAUNCHD_OK)
    discovery = next(c for c in checks if c.name == "discovery")
    assert discovery.status == "warn" and "careers-browser" in discovery.detail


def test_browser_counts_are_reported(tmp_path):
    checks = health.run_checks(DAY, setup_day(tmp_path), recipient="x@y.z", launchd_output=LAUNCHD_OK)
    discovery = next(c for c in checks if c.name == "discovery")
    assert discovery.status == "ok" and "browser: 2" in discovery.detail


# daily.sh appends every attempt of a day (08:00 + catch-ups) to one log; only the last one counts.
_START = "=== Fri Nov 13 08:00:01 CET 2026 daily digest start\n"
_FAILED = (_START + "API Error: Can't reach the API server (ENOTFOUND)\n"
           "=== Fri Nov 13 08:42:28 CET 2026 daily digest end (exit 1)\n")
_OK = _START.replace("08:00", "11:00") + "=== Fri Nov 13 11:20:46 CET 2026 daily digest end (exit 0)\n"
_SKIP = "=== Fri Nov 13 14:05:00 CET 2026 no network after 5 minutes (Mac asleep or offline); skipped\n"


@pytest.mark.parametrize("log,expected", [
    (_FAILED + _OK, "ok"),             # failed 08:00, catch-up succeeded (2026-11-13)
    (_OK + _FAILED, "fail"),
    (_SKIP + _OK, "ok"),
    (_OK + _SKIP, "ok"),               # the last *started* attempt is judged
    (_SKIP + _FAILED, "fail"),
    (_FAILED + _SKIP, "fail"),
    (_SKIP, "fail"),                   # no attempt started at all
    (_FAILED + _START, "warn"),        # last attempt still running
])
def test_run_log_judges_only_the_last_attempt(tmp_path, log, expected):
    paths = setup_day(tmp_path, log=log)
    assert health.check_run_log(DAY, paths).status == expected


def test_run_log_counts_earlier_attempts(tmp_path):
    paths = setup_day(tmp_path, log=_FAILED + _FAILED + _OK)
    check = health.check_run_log(DAY, paths)
    assert check.status == "ok" and "2 earlier attempt" in check.detail


def test_skip_only_log_says_no_network(tmp_path):
    check = health.check_run_log(DAY, setup_day(tmp_path, log=_SKIP))
    assert "no network" in check.detail


def test_start_marker_inside_claude_output_is_ignored(tmp_path):
    # Only daily.sh's own "=== ... daily digest start" line starts an attempt.
    # A substring match on the later mention would cut off the traceback before it.
    log = (_START + "Traceback (most recent call last)\n"
           "Retrying the daily digest start\n"
           "=== Fri Nov 13 08:30:00 CET 2026 daily digest end (exit 0)\n")
    assert health.check_run_log(DAY, setup_day(tmp_path, log=log)).status == "fail"


@pytest.mark.parametrize("reason", [
    "lid closed on battery (dark wake)",
    "attempt limit (3) reached",
    "no network after 5 minutes (Mac asleep or offline)",
])
def test_skip_only_log_names_the_last_skip_reason(tmp_path, reason):
    # daily.sh writes "=== <date> <reason>; skipped" when it skips a start without launching Claude.
    log = ("=== Sat Nov 14 08:25:02 CET 2026 lid closed on battery (dark wake); skipped\n"
           f"=== Sat Nov  1 09:00:00 CET 2026 {reason}; skipped\n")
    check = health.check_run_log(DAY, setup_day(tmp_path, log=log))
    assert check.status == "fail"
    assert check.detail.endswith(f"last skip: {reason}")

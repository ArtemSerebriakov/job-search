import json
from datetime import date

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

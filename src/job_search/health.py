"""Operational checks for one day's run: did the 08:00 job actually work?

Unit tests cover the logic; these checks cover the run. Each check is a plain function over files the
run leaves behind (logs, batch files, the report), plus launchd's status. `jobsearch check-run`
prints them; the check-run skill adds the one thing Python cannot see: whether the email arrived.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from job_search import scoring
from job_search.dedup import REPORT_GLOB, normalize_url, urls_in_reports

Status = Literal["ok", "warn", "fail"]
LAUNCHD_LABEL = "com.job-search.daily"
_URL_RE = re.compile(r"\]\((https?://[^)\s]+)\)")
_LOG_ERRORS = re.compile(
    r"(operation not permitted|permission denied|not logged in|please run /login|authentication|"
    r"traceback \(most recent call last\)|^error:|command not found|daily digest end \(exit [1-9])",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class Check:
    name: str
    status: Status
    detail: str


@dataclass
class Paths:
    data_dir: Path
    reports_dir: Path
    logs_dir: Path

    def batch(self, day: date) -> Path:
        return self.data_dir / "batches" / day.isoformat()


def launchd_status() -> str | None:
    """`launchctl print` output for the job, or None if it is not loaded."""
    import os

    result = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{LAUNCHD_LABEL}"],
                            capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else None


def check_launchd(output: str | None) -> Check:
    if output is None:
        return Check("launchd", "fail", "the 08:00 job is not loaded — run scripts/install-schedule.sh --check")
    if re.search(r"^\s*state = running", output, re.MULTILINE):
        return Check("launchd", "ok", "job is running now")
    code = re.search(r"last exit code = (-?\d+)", output)
    runs = re.search(r"runs = (\d+)", output)
    if not code:
        return Check("launchd", "warn", "job loaded but has not run yet")
    exit_code = int(code.group(1))
    if exit_code == 0:
        return Check("launchd", "ok", f"last run exited 0 ({runs.group(1) if runs else '?'} runs since loaded)")
    hint = " — macOS blocked Desktop access; see logs/launchd.err.log" if exit_code == 126 else ""
    return Check("launchd", "fail", f"last run exited {exit_code}{hint}")


def check_run_log(day: date, paths: Paths) -> Check:
    err_log = paths.logs_dir / "launchd.err.log"
    launchd_errors = err_log.read_text().strip() if err_log.exists() else ""
    log = paths.logs_dir / f"{day.isoformat()}.log"
    if not log.exists():
        detail = f"no logs/{log.name} — the digest never started"
        if launchd_errors:
            detail += f"; launchd: {launchd_errors.splitlines()[-1][:160]}"
        return Check("run log", "fail", detail)
    text = log.read_text()
    errors = [m.group(0) for m in _LOG_ERRORS.finditer(text)]
    if errors:
        return Check("run log", "fail", f"errors in logs/{log.name}: {'; '.join(dict.fromkeys(errors))[:200]}")
    if "daily digest end (exit 0)" not in text:
        return Check("run log", "warn", f"logs/{log.name} has no clean end marker (still running or killed?)")
    return Check("run log", "ok", f"logs/{log.name} ended with exit 0")


def check_sources(day: date, paths: Paths) -> Check:
    path = paths.batch(day) / "collect.json"
    if not path.exists():
        return Check("sources", "fail", "no collect.json — collect did not run")
    results = json.loads(path.read_text())
    failed = {name: r["error"] for name, r in results.items() if r.get("error")}
    total = sum(r.get("relevant", 0) for r in results.values())
    if failed and len(failed) == len(results):
        return Check("sources", "fail", f"all {len(results)} sources failed, e.g. {next(iter(failed.values()))[:120]}")
    if failed:
        names = ", ".join(f"{n} ({e[:60]})" for n, e in list(failed.items())[:3])
        return Check("sources", "warn", f"{len(failed)} of {len(results)} sources failed: {names}")
    return Check("sources", "ok", f"all {len(results)} sources OK, {total} relevant postings")


def _count(path: Path) -> int:
    items = json.loads(path.read_text())
    return len(json.loads(items) if isinstance(items, str) else items)


def check_discovery(day: date, paths: Paths) -> Check:
    batch = paths.batch(day)
    expected = {"discovered.json": "web-discovery", "discovered_connectors.json": "connector-discovery"}
    missing = [agent for name, agent in expected.items() if not (batch / name).exists()]
    counts = {name.removesuffix(".json"): _count(batch / name) for name in expected if (batch / name).exists()}
    browser_files = sorted(batch.glob("discovered_browser_*.json"))
    if browser_files:
        counts["browser"] = sum(_count(f) for f in browser_files)
    else:
        missing.append("careers-browser")
    summary = ", ".join(f"{n}: {c}" for n, c in counts.items())
    if len(missing) == len(expected) + 1:
        return Check("discovery", "fail", "no discovery agent wrote its file")
    if missing:
        return Check("discovery", "warn", f"{', '.join(missing)} wrote nothing; {summary}")
    return Check("discovery", "ok", summary)


def check_scoring(day: date, paths: Paths) -> Check:
    batch = paths.batch(day)
    if not (batch / "to_score.json").exists():
        return Check("scoring", "fail", "no to_score.json — prepare did not run")
    expected = {x["posting_id"] for x in json.loads((batch / "to_score.json").read_text())}
    if not expected:
        return Check("scoring", "ok", "nothing to score today")
    _, problems = scoring.load_and_validate(batch / "scores.json", expected)
    if problems:
        return Check("scoring", "warn" if (batch / "scores.json").exists() else "fail",
                     f"{len(problems)} scoring problems, e.g. {problems[0][:120]}")
    return Check("scoring", "ok", f"{len(expected)} postings scored, all valid")


def _report_path(day: date, paths: Paths) -> Path:
    return paths.reports_dir / REPORT_GLOB.replace("*", day.isoformat())


def check_report(day: date, paths: Paths) -> Check:
    path = _report_path(day, paths)
    if not path.exists():
        return Check("report", "fail", f"no {path.name} — finalize did not run")
    n = len(_URL_RE.findall(path.read_text()))
    return Check("report", "ok" if n else "warn", f"{n} postings reported")


def check_dedup(day: date, paths: Paths) -> Check:
    path = _report_path(day, paths)
    if not path.exists():
        return Check("dedup", "warn", "no report to check")
    today = {normalize_url(u) for u in _URL_RE.findall(path.read_text())}
    repeated = today & urls_in_reports(paths.reports_dir, before=day)
    if repeated:
        return Check("dedup", "fail", f"{len(repeated)} URL(s) already reported earlier, e.g. {sorted(repeated)[0]}")
    return Check("dedup", "ok", "no posting repeated from earlier days")


def check_recipient(recipient: str | None) -> Check:
    if not recipient:
        return Check("recipient", "fail", "DIGEST_RECIPIENT is not set in .env — the email cannot be sent")
    return Check("recipient", "ok", f"emails go to {recipient}")


def check_email(day: date, paths: Paths) -> Check:
    path = paths.batch(day) / "email_sent.json"
    if not path.exists():
        return Check("email", "fail", "no email_sent.json — the email step did not complete")
    sent = json.loads(path.read_text())
    return Check("email", "ok", f"sent (Gmail message {sent.get('message_id', '?')})")


def run_checks(day: date, paths: Paths, recipient: str | None, launchd_output: str | None) -> list[Check]:
    return [
        check_launchd(launchd_output),
        check_run_log(day, paths),
        check_sources(day, paths),
        check_discovery(day, paths),
        check_scoring(day, paths),
        check_report(day, paths),
        check_dedup(day, paths),
        check_recipient(recipient),
        check_email(day, paths),
    ]


def exit_code(checks: list[Check]) -> int:
    return 1 if any(c.status == "fail" for c in checks) else 0


def render(day: date, checks: list[Check]) -> str:
    icons = {"ok": "✓", "warn": "⚠", "fail": "✗"}
    lines = [f"check-run {day.isoformat()}"]
    lines += [f"  {icons[c.status]} {c.name:10} {c.detail}" for c in checks]
    fails = sum(c.status == "fail" for c in checks)
    warns = sum(c.status == "warn" for c in checks)
    lines.append(f"result: {'FAIL' if fails else 'OK'} ({fails} failed, {warns} warnings)")
    return "\n".join(lines)

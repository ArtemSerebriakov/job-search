---
name: check-run
description: Check whether a day's scheduled 08:00 job-digest run actually worked — launchd exit code, run log errors, failed sources, discovery output, scoring, report, repeated URLs, recipient, and whether the email arrived in Gmail. Use when the user asks if the morning run worked, why no email came, or to verify the app end to end.
---

# Check a day's run

1. Run `uv run jobsearch check-run` (add `--date YYYY-MM-DD` for another day). It prints one line per
   check (✓ ok, ⚠ warning, ✗ failed) and exits 1 if anything failed. Python decides these; don't
   re-derive them.
2. Confirm delivery in Gmail (Python cannot see this): search threads with
   `subject:"Job digest <date>" newer_than:3d`. Report whether it arrived and when. If it didn't,
   check Spam: `in:spam subject:"Job digest <date>"`.
3. Summarise for the user: overall OK/FAIL, each failure in plain words, and the fix from the table
   below. Read `logs/<date>.log` or `logs/launchd.err.log` only as needed to explain a failure.

| Symptom | Likely cause | Fix |
|---|---|---|
| launchd exit 126, "Operation not permitted" | macOS blocked Desktop access | `scripts/install-schedule.sh --check`, then allow JobSearchRunner |
| launchd: job not loaded | schedule not installed | `scripts/install-schedule.sh --check` |
| no run log, launchd exit 0 | Mac was off/asleep all morning, or the runner app failed | check `logs/launchd.err.log`; run `launchctl kickstart gui/$(id -u)/com.job-search.daily` |
| run log: "not logged in" / authentication | Claude Code logged out | log in with `claude` interactively |
| sources: jobspipe failed (402/401) | JobsPipe credits used up or key invalid | top up credits or fix `JOBSPIPE_API_KEY` in `.env` |
| sources: all failed | no network at run time | rerun the digest |
| discovery: an agent wrote nothing | connector disconnected or rate-limited | reconnect it in claude.ai settings |
| scoring problems | scorer returned invalid JSON | the report lists them; usually transient |
| dedup: URL repeated | dedup bug | treat as a leak: use `/fix-leak` |
| recipient missing | `DIGEST_RECIPIENT` not in `.env` | the user adds it (never read `.env` yourself) |
| email: no email_sent.json, but it arrived | the run sent it but didn't record it | harmless; note it |

Never send the digest, rerun the pipeline or spend JobsPipe credits from this skill without asking.

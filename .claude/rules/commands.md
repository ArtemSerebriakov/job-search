# Commands

Environment: uv-managed `.venv`, prompt name `job-search`, Python 3.12.

## Setup
- `uv sync` — create/refresh the environment from `uv.lock`

## Tests
- `uv run pytest` — full suite (run after every significant change)
- `uv run pytest tests/test_verify_seniority.py -q` — a single rule

All commands accept `--date YYYY-MM-DD` (default: today).

## Pipeline (normally driven by the `daily-digest` skill)
1. `uv run jobsearch collect` — fetch API/ATS sources into SQLite
2. (Claude web discovery writes `data/batches/<date>/discovered.json`)
   `uv run jobsearch ingest-discovered`
3. `uv run jobsearch prepare` — dedup → verify → liveness → embedding rank → `to_score.json`
   (`--dry-run` prints the exclusion audit without writing; `--no-liveness` skips HTTP checks)
4. (Claude writes `data/batches/<date>/scores.json`)
5. `uv run jobsearch finalize` — validate scores → cross-check → weight → write report
   (exit 3 = invalid/missing scores; re-score those, then `finalize --allow-partial`)
6. `uv run jobsearch log-outcome <posting-id> --status sent|reply|interview|rejected`
7. `uv run jobsearch status` — counts, calibration state

## Scheduling
- `scripts/daily.sh` runs `claude -p "/daily-digest" --model sonnet` with an explicit
  `--allowedTools` list and PATH; logs to `logs/<date>.log`.
- At 08:00 (on wake if asleep) launchd runs `open -W -g -a ~/Applications/JobSearchRunner.app`; the
  app runs `scripts/daily.sh`. Why an app: macOS blocks bare launchd jobs from reading ~/Desktop
  ("Operation not permitted", exit 126 — the 2026-10-24 run failed this way). The Desktop permission
  is granted to the app once and inherited by every run.
- Templates: `launchd/com.job-search.daily.plist.template`, `launchd/JobSearchRunner.applescript.template`.
- Install / reinstall (only with the user's OK): `scripts/install-schedule.sh` — builds the app if
  missing, renders the plist, loads it. `--check` also runs a harmless permission check (writes
  `logs/permission-check.log`; no email, no credits). `--rebuild-runner` rebuilds the app, which makes
  macOS forget the Desktop permission.
- Verify the real path without sending email: `touch ~/.job-search-permission-check && launchctl kickstart gui/$(id -u)/com.job-search.daily`,
  then read `logs/permission-check.log`. Verified this way on 2026-10-24.
- Never call the Desktop access "verified" from a check started inside an interactive session: it
  inherits the terminal's/editor's permission (that is how the 2026-10-23 probe passed misleadingly).
- Status: `launchctl print gui/$(id -u)/com.job-search.daily`
- Uninstall: `launchctl bootout gui/$(id -u)/com.job-search.daily && rm ~/Library/LaunchAgents/com.job-search.daily.plist`
- Run now (sends the email, spends JobsPipe credits): `launchctl kickstart gui/$(id -u)/com.job-search.daily`
- Logs: `logs/<date>.log` (the Claude run), `logs/launchd.err.log` (launchd itself).

## Claude Code project settings
- `.claude/settings.json` hook: after Edit/Write on `src/job_search/verify/*`, `dedup.py`,
  `config.py`, `tests/*` or `config/criteria.yaml`, runs `uv run pytest -q`. Exit 2 means
  tests failed; read the output and fix it before moving on.
- Review or disable hooks via `/hooks`.

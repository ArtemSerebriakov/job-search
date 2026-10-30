# job-search

A daily agent that finds **new entry-level AI / ML / NLP / Data Science postings**, rejects every
posting that fails the hard criteria with deterministic, tested Python rules, ranks the rest
against the CV with a local multilingual embedding model, has Claude (Sonnet) score the top 25,
and emails the top 10 as a digest every morning at 08:00.

Principle: **the model judges, the code decides.** Claude only discovers postings and returns
sub-scores as schema-validated JSON; every accept/reject decision, weight and threshold is Python.

## How it works
1. **Collect** — public job feeds of 21 named companies (Greenhouse, Ashby, Workable, Teamtailor,
   Personio, Lever, Pinpoint), Bundesagentur für Arbeit, Arbeitnow, Himalayas, RemoteOK, and the JobsPipe API
   (30+ boards incl. EURES, Bayt, LinkedIn; also covers the 11 named companies with custom careers
   sites) (`config/sources.yaml`).
2. **Discover** — the `web-discovery` agent searches boards without an API and custom careers
   sites; the `connector-discovery` agent searches the Indeed, JobDataLake and Workable connectors;
   the `careers-browser` agent opens named companies' JavaScript-only careers pages in a headless,
   isolated browser (job boards blocked; bot checks are never bypassed).
3. **Verify** — hard filters: already reported, direct link, location, Werkstudent/intern,
   seniority (0–2 years), description in English or Russian, no German fluency requirement
   (intermediate German is flagged), still open. Same-day duplicates collapsed.
4. **Rank** — similarity of the title and the best-matching description window to
   `config/profile.md`; top 25 go to Claude.
5. **Score** — the `posting-scorer` agent returns 5 sub-scores plus extracted facts with quotes;
   Python weights them, adds a location bonus (Munich first), re-checks the facts, keeps the top 10.
6. **Report and email** — `reports/job-search_daily-reports_<date>.md`, emailed via the Gmail connector.
7. **Calibrate** — log what happened to each application; after 30 resolved outcomes the score is
   mapped to a measured reply probability.

## Install
Requires [uv](https://docs.astral.sh/uv/) and Claude Code (logged in, with the Gmail connector).

```bash
git clone https://github.com/ArtemSerebriakov/job-search.git && cd job-search
uv sync                       # creates .venv (prompt name: job-search)
source .venv/bin/activate     # optional; `uv run …` works without activating
```
Open the folder in Claude Code once and accept the trust prompt, so `.claude/settings.json` applies.

Personal settings (all git-ignored, never committed):
- `cp config/profile.example.md config/profile.md` and replace it with your CV text.
- `cp .env.example .env`, then set `DIGEST_RECIPIENT` (the only address the digest is emailed to)
  and `JOBSPIPE_API_KEY`.

JobsPipe needs an API key (`JOBSPIPE_API_KEY`).
Without it, `collect` skips JobsPipe and reports why. The free plan has 1,000 one-off credits
(one per returned job); `config/sources.yaml` caps spending at 30 per day.

The Indeed, JobDataLake and Jobs by Workable connectors must be connected in your claude.ai account.
The first `prepare` downloads the embedding model (~220 MB) into `data/models/`.

## Run
Whole pipeline, as the scheduler runs it:
```bash
scripts/daily.sh              # headless; log in logs/<date>.log
```
Or interactively in Claude Code: `/daily-digest`.

Individual steps:
```bash
uv run jobsearch collect                 # fetch all API sources
uv run jobsearch prepare --dry-run       # filters only; prints the exclusion audit
uv run jobsearch prepare                 # filters + ranking → data/batches/<date>/to_score.json
uv run jobsearch finalize                # needs scores.json from the posting-scorer agent
uv run jobsearch log-outcome <id> --status sent|reply|interview|rejected
uv run jobsearch status
uv run jobsearch check-run              # did today's scheduled run work? (exit 1 on failure)
```
In Claude Code, `/check-run` runs the same checks and also confirms the email arrived in Gmail.
If a morning run fails, a macOS notification tells you.

Schedule (08:00 daily; runs on wake if the Mac was asleep):
```bash
scripts/install-schedule.sh --check                      # install; approve the macOS Desktop-access prompt
launchctl print gui/$(id -u)/com.job-search.daily        # status
launchctl kickstart gui/$(id -u)/com.job-search.daily    # run now
launchctl bootout gui/$(id -u)/com.job-search.daily      # stop
```
Logs: `logs/<date>.log`.

macOS blocks background jobs from reading `~/Desktop`, so launchd opens a tiny app,
`~/Applications/JobSearchRunner.app` (built by the installer), which runs `scripts/daily.sh`.
You allow its Desktop access once; every later run inherits it.

## Tests
```bash
uv run pytest
```
No test touches the network: sources are tested on recorded payloads in `tests/fixtures/`.

## Project structure
```
.claude/            CLAUDE.md, rules/, settings.json (permissions + test hook),
                    skills/ (daily-digest, fix-leak, check-run, commit-msg),
                    agents/ (web-discovery, connector-discovery, careers-browser, posting-scorer)
config/
  criteria.yaml     named companies, countries, weights, thresholds, embedding model
  sources.yaml      company job feeds, board queries, browser careers sites
  browser-mcp.json  headless Playwright config for the careers-browser agent
  browser_extract.js  posting extraction script run in the browser
  profile.example.md  template for your CV (copy to profile.md, git-ignored)
src/job_search/
  cli.py            jobsearch command
  sources/          job feeds (ats.py: Greenhouse, Ashby, Workable, Teamtailor, Personio, Lever,
                    Pinpoint), job boards (boards.py), JobsPipe, title pre-filter, registry
  verify/           hard filters + pipeline
  dedup.py          URL normalisation, report history, repost and same-day duplicates
  rank.py           embedding pre-filter
  scoring.py        score validation, fact cross-check, weighting
  calibration.py    reply-probability calibration with censoring
  report.py         markdown digest
  health.py         check-run: health of a day's scheduled run
  db.py, models.py, config.py
scripts/            daily.sh (headless run), install-schedule.sh
launchd/            the 08:00 schedule and the runner app (templates)
reports/            daily reports (local, git-ignored: they are the dedup history)
data/               SQLite DB, daily batches, model cache (git-ignored)
tests/              pytest suite
```

## Status and next steps
**Works**
- All sources collect live data (486 relevant postings on the first run, 22 sources, no errors).
- Verification, ranking, scoring validation, report with HTML/plain-text email, calibration, CLI,
  run health checks (`check-run`) with failure notifications; 268 tests.
- Hiring-platform feeds for 21 named companies, including Lever (Finom) and Pinpoint (Tabby, inDrive).
- Browser discovery for named companies' careers sites: EPAM, DataArt, Andersen, Belitsoft, Luxoft
  (Revolut, Qdrant, Wirex excluded: bot checks; Kaspi, Yango, Uzum: no reachable listing).
- Scheduled 08:00 runs through the runner app work end to end: digests emailed on 2026-10-25, -26,
  -27, -29 and -30 (2026-10-30: 6 postings, no repeated URLs; JobsPipe timed out once).
- Job connectors (Indeed, JobDataLake, Workable) via the `connector-discovery` agent; JobsPipe API
  source (needs `JOBSPIPE_API_KEY` in `.env`).
- Headless Claude Code can reach the Gmail connector.

**Next**
1. Find out why 2026-10-28 has no run (no log; `check-run --date 2026-10-28`): probably the Mac
   was off all morning.
2. Check the Moss "seasoned engineer" posting with `/fix-leak`.
3. Put the full CV into `config/profile.md` for sharper ranking and scoring.
4. Review exclusion audits from the first week for false rejections (`/fix-leak`).

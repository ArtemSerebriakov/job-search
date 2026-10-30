# job-search

Daily agent that collects new job postings, rejects anything that fails the hard criteria
(deterministic, tested Python rules), ranks the rest against the CV with local embeddings,
has Claude score the top 25, and emails the top 10 as a digest.

Core principle: **the model judges, the code decides.**

## Key commands
- Tests: `uv run pytest` (also run automatically by a hook after edits to verify/, dedup, config or tests)
- Daily run (headless): `claude -p "/daily-digest"` — see rules/commands.md for the full pipeline.

## Rules index
- [rules/commands.md](rules/commands.md) — setup, pipeline, test and scheduling commands
- [rules/architecture.md](rules/architecture.md) — pipeline steps and where each decision lives
- [rules/verification.md](rules/verification.md) — the hard-filter rules and how to change them
- [rules/criteria.md](rules/criteria.md) — the user's search criteria (source of truth for the rules)
- [rules/conventions.md](rules/conventions.md) — code style, file layout, naming, secrets

## Skills
- `/daily-digest` — the full daily pipeline (collect → discover → prepare → score → finalize → email)
- `/fix-leak` — a wrong posting got through (or a good one was rejected): failing test first, then fix the rule
- `/check-run` — did a day's 08:00 run work? Runs `uv run jobsearch check-run` and confirms the email in Gmail

## Agents
- `web-discovery` — finds postings on boards without an API and writes `discovered.json`
- `connector-discovery` — searches the Indeed, JobDataLake and Workable connectors (read-only tools) and writes `discovered_connectors.json`
- `careers-browser` — headless, isolated browser for named companies' careers sites listed under `browser_careers` in `config/sources.yaml`; writes `discovered_browser_*.json`
- `posting-scorer` — five sub-scores plus extracted facts as JSON; never decides eligibility

## Settings (`settings.json`)
- Allowed: `uv run pytest`, `uv run jobsearch`, `uv sync`, WebSearch/WebFetch, and writes to `data/batches/` and `reports/`.
- Asks first: git commit/push/remote, launchctl, editing `config/criteria.yaml`.
- Denied: reading `.env` (holds `JOBSPIPE_API_KEY`; see `.env.example`).
- Hook: after an Edit/Write to the verification code, config or tests, `uv run pytest -q` runs. A failure is reported back immediately.

# Conventions

- Python 3.12, package `src/job_search`, CLI entry point `jobsearch`.
- Type hints everywhere; pydantic models in `models.py`; config is YAML in `config/`.
- Rules in `verify/` are pure functions with no I/O, except `liveness.py` (HTTP via httpx,
  injectable client so tests never hit the network).
- Tests in `tests/`, one file per verify rule; no network in tests.
- Runtime data in `data/` (git-ignored except `.gitkeep`); per-day files in `data/batches/<YYYY-MM-DD>/`.
- Reports: `reports/job-search_daily-reports_<YYYY-MM-DD>.md` (local, git-ignored; they are the dedup history).
- The repository is public. Personal data stays local and git-ignored: the CV (`config/profile.md`),
  daily reports (`reports/*.md`), the recipient address (`DIGEST_RECIPIENT` in `.env`), the DB and
  batches. No absolute paths with a username in tracked files (launchd uses a template).
- Secrets only in `.env` (git-ignored; template `.env.example`), loaded by `config.load_env()`.
  Never commit tokens or keys.
- Job connectors: agents get read-only search/detail tools only — never profile, résumé,
  application, billing or alert-creating tools (Workable `update_my_profile`/`withdraw_application`,
  Indeed `get_resume`, JobsPipe `upgrade_plan`/`create_signal`).
- Dependencies via `uv add` only, after the user approves them.

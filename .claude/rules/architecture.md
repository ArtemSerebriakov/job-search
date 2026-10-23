# Architecture

The model judges, the code decides. Claude only (a) discovers postings on boards without an
API and (b) returns sub-scores + extracted facts as JSON. Every accept/reject decision,
weighting, threshold and ranking happens in Python.

## Daily flow
1. `collect` — `src/job_search/sources/*` (configured in `config/sources.yaml`) → title pre-filter
   (`sources/relevance.py`) → `postings` table (SQLite, `data/jobs.db`). One failing source never
   stops the run. JobsPipe (`sources/jobspipe.py`) is a paid API: one credit per returned job, capped by
   `jobspipe.max_results_per_day`; filters run on JobsPipe's side to avoid paying for rejects.
2. Claude discovery, two agents in parallel: `web-discovery` (boards without an API, custom careers
   sites) → `discovered.json`; `connector-discovery` (Indeed, JobDataLake, Workable connectors,
   read-only tools) → `discovered_connectors.json`; then `ingest-discovered` reads every `discovered*.json`
3. `prepare`
   - `dedup.py`: drop URLs already in `seen_urls` or in any earlier
     `reports/job-search_daily-reports_*.md`; drop reposts (same company + normalised title)
     unless the earlier record was closed
   - `verify/pipeline.py`: hard rules; any FAIL excludes, FLAG keeps with a warning
   - liveness check against the source (ATS / company page), not the aggregator
   - `dedup.collapse_duplicates`: one posting per company + title within the day
   - `rank.py`: fastembed multilingual model (`criteria.yaml: embedding_model`); similarity =
     0.5·cos(title, profile) + 0.5·max cos(500-char description window, profile) → top 25
     (the small model reads ~128 tokens and postings open with boilerplate, hence windows); writes `to_score.json` and `prepare.json` (funnel, audit, flags)
4. Claude scoring (`posting-scorer` agent) → `scores.json`
5. `finalize` — `scoring.py` validates the JSON (pydantic), cross-checks LLM facts against
   rule verdicts (stricter wins + flag), applies weights from `config/criteria.yaml`, location
   bonus, threshold, top 10 → `report.py` writes the markdown report
6. Claude emails the report via the Gmail connector (to the user's own address only)

## Calibration
`calibration.py`: until 30 resolved outcomes, scores are labelled "uncalibrated fit estimate".
Afterwards a logistic map score → P(reply) is fitted. Pending applications are censored
(excluded) until `no_reply_after_days` (config) passes, then count as no reply.

## Report and dedup coupling
The next day's dedup reads every URL in earlier reports, so the report links only reported
postings; excluded ones are listed by title and company only.

## Never
- Never let LLM extracted facts lower sub-scores (double-counting bug in the reference design).
- Never pad the digest: fewer than 10 passing postings → report fewer and say so.

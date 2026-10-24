"""`jobsearch` command line: collect → ingest-discovered → prepare → finalize, plus outcome logging."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

from pydantic import ValidationError

from job_search import calibration, health, rank, report, scoring
from job_search.config import DATA_DIR, LOGS_DIR, REPORTS_DIR, digest_recipient, load_criteria, load_env, load_profile
from job_search.db import DB
from job_search.dedup import collapse_duplicates, urls_in_reports
from job_search.models import Posting, Verdict
from job_search.sources.base import make_client, run_source
from job_search.sources.registry import build_sources, load_sources_config
from job_search.verify import liveness, location
from job_search.verify.pipeline import verify

OUTCOME_STATUSES = ("sent", "reply", "interview", "rejected")
EXIT_SCORING_PROBLEMS = 3


# Indirections so tests can swap paths, sources and the embedding model.
def data_dir() -> Path:
    return DATA_DIR


def reports_dir() -> Path:
    return REPORTS_DIR


def logs_dir() -> Path:
    return LOGS_DIR


def get_embedder(model_name: str) -> rank.Embedder:
    return rank.fastembed_embedder(model_name)


def get_sources(client):
    return build_sources(client, load_sources_config())


def batch_dir(day: date) -> Path:
    return data_dir() / "batches" / day.isoformat()


def open_db() -> DB:
    return DB(data_dir() / "jobs.db")


# --- commands -------------------------------------------------------------------------------------

def cmd_collect(args) -> int:
    db = open_db()
    total_new = 0
    summary: dict[str, dict] = {}
    with make_client() as client:
        for name, fetch in get_sources(client):
            result = run_source(name, fetch)
            if result.error:
                print(f"  {name:32} ERROR {result.error}")
                summary[name] = {"relevant": 0, "new": 0, "error": result.error}
                continue
            new = db.upsert_postings(result.postings, args.date)
            total_new += new
            summary[name] = {"relevant": len(result.postings), "new": new, "error": None}
            print(f"  {name:32} {len(result.postings):4} relevant, {new:4} new")
    out = batch_dir(args.date)
    out.mkdir(parents=True, exist_ok=True)
    (out / "collect.json").write_text(json.dumps(summary, indent=2))  # read by check-run
    print(f"collect: {total_new} new postings stored for {args.date}")
    return 0


def cmd_ingest_discovered(args) -> int:
    """Ingest discovered*.json from today's batch (web-discovery and connector-discovery agents)."""
    paths = [args.file] if args.file else sorted(batch_dir(args.date).glob("discovered*.json"))
    if not paths:
        print(f"ingest-discovered: no discovered*.json in {batch_dir(args.date)} — nothing to ingest")
        return 0
    db = open_db()
    for path in paths:
        items = json.loads(path.read_text())
        valid, skipped = [], 0
        for item in items:
            try:
                item = {**item, "source": item.get("source") or "discovery"}
                valid.append(Posting.model_validate(item))
            except ValidationError as exc:
                skipped += 1
                print(f"  skipped invalid entry {item.get('url', '?')}: {exc.errors()[0]['msg']}")
        new = db.upsert_postings(valid, args.date)
        print(f"ingest-discovered {path.name}: {len(valid)} valid ({new} new), {skipped} skipped")
    return 0


def _label(p: Posting) -> str:
    return f"{p.title} — {p.company}"


def cmd_prepare(args) -> int:
    criteria = load_criteria()
    db = open_db()
    day = args.date
    postings = db.postings_seen_on(day)
    reported = urls_in_reports(reports_dir(), before=day) | db.reported_urls(day)
    fingerprints = db.reported_fingerprints(day)

    results = {p.id: verify(p, criteria, reported, fingerprints) for p in postings}
    by_id = {p.id: p for p in postings}

    if not args.no_liveness:
        candidates = [pid for pid, r in results.items() if r.passed]
        with make_client() as client, ThreadPoolExecutor(max_workers=8) as pool:
            verdicts = pool.map(lambda pid: liveness.check(by_id[pid], client), candidates)
            for pid, verdict in zip(candidates, verdicts):
                results[pid].verdicts.append(verdict)
                if verdict.status == "fail":
                    db.mark_closed(pid)

    audit: dict[str, list[str]] = defaultdict(list)
    passing: list[Posting] = []
    for pid, result in results.items():
        if result.passed:
            passing.append(by_id[pid])
        else:
            audit[result.failures[0].rule].append(_label(by_id[pid]))
        if not args.dry_run:
            db.save_verdicts(pid, day, result.verdicts)
    new_count = len(postings) - len(audit.get("dedup", []))
    passing, duplicates = collapse_duplicates(passing)
    if duplicates:
        audit["same-day duplicate"] = [_label(p) for p in duplicates]

    print(f"prepare {day}: {len(postings)} collected → {new_count} new → {len(passing)} passed filters")
    for rule, labels in sorted(audit.items(), key=lambda kv: -len(kv[1])):
        print(f"  excluded by {rule:22} {len(labels):4}   e.g. {'; '.join(labels[:2])[:110]}")
    if args.dry_run:
        print("dry run: nothing written")
        return 0

    ranked = rank.rank(load_profile(), passing, criteria.prefilter_top_k, get_embedder(criteria.embedding_model))
    out = batch_dir(day)
    scoring.write_to_score(out / "to_score.json", ranked)
    meta = {
        "date": day.isoformat(), "collected": len(postings), "new": new_count, "passed": len(passing),
        "audit": audit,
        "flags": {p.id: [v.model_dump() for v in results[p.id].flags] for p, _ in ranked},
        "similarity": {p.id: round(sim, 4) for p, sim in ranked},
    }
    (out / "prepare.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"wrote {len(ranked)} postings to {out / 'to_score.json'}")
    return 0


def cmd_finalize(args) -> int:
    criteria = load_criteria()
    db = open_db()
    day = args.date
    out = batch_dir(day)
    meta = json.loads((out / "prepare.json").read_text())
    to_score = json.loads((out / "to_score.json").read_text())
    expected = {item["posting_id"] for item in to_score}

    results, problems = scoring.load_and_validate(out / "scores.json", expected) if expected else ({}, [])
    if problems and not args.allow_partial:
        print("finalize: scores.json has problems — re-score these postings, then run "
              "`jobsearch finalize --allow-partial`:")
        for problem in problems:
            print(f"  {problem}")
        return EXIT_SCORING_PROBLEMS

    audit: dict[str, list[str]] = defaultdict(list, meta["audit"])
    entries: list[report.Entry] = []
    for pid, result in results.items():
        posting = db.get_posting(pid)
        checks = scoring.cross_check(result, posting, criteria)
        fails = [v for v in checks if v.status == "fail"]
        score = scoring.final_score(result, location.location_bonus(posting, criteria), criteria)
        db.save_score(pid, day, result.model_dump(), score)
        if fails:
            audit[scoring.RULE].append(_label(posting))
            db.save_verdicts(pid, day, checks)
            continue
        flags = [Verdict(**v) for v in meta["flags"].get(pid, [])] + [v for v in checks if v.status == "flag"]
        if score >= criteria.min_final_score:
            entries.append(report.Entry(posting, score, result, flags))
        else:
            audit["below score threshold"].append(_label(posting))

    entries.sort(key=lambda e: -e.score)
    entries = entries[: criteria.digest_size]

    outcomes = [dict(row) for row in db.outcomes_with_scores()]
    calib = calibration.Calibrator.from_outcomes(outcomes, day, criteria.calibration)
    chance = calib.chance([e.score for e in entries[:3]]) if entries else 0.0
    chance_avg = _seven_day_average(db, calib, day, chance)

    funnel = report.Funnel(meta["collected"], meta["new"], meta["passed"], len(results), len(entries))
    content = report.render(day, entries, criteria.digest_size, chance, chance_avg, calib.note(), funnel,
                            dict(audit), problems)
    path = report.write(reports_dir(), day, content)
    html_path, text_path = report.write_email(out, content)
    db.save_reported(day, [(e.posting, e.score) for e in entries])
    print(f"finalize: {len(entries)} postings reported → {path}")
    print(f"email: subject 'Job digest {day.isoformat()} — {len(entries)} new roles'; "
          f"htmlBody {html_path}; body {text_path}")
    recipient = digest_recipient()
    print(f"email: to {recipient}" if recipient else "email: recipient not configured — set DIGEST_RECIPIENT in .env")
    return 0


def _seven_day_average(db: DB, calib: calibration.Calibrator, day: date, today_chance: float) -> float | None:
    by_day: dict[str, list[float]] = defaultdict(list)
    for row in db.daily_chances(day - timedelta(days=6)):
        if row["run_date"] != day.isoformat() and row["rank"] <= 3:
            by_day[row["run_date"]].append(row["final_score"])
    chances = [calib.chance(scores) for scores in by_day.values()] + [today_chance]
    return sum(chances) / len(chances) if len(chances) > 1 else None


def cmd_log_outcome(args) -> int:
    db = open_db()
    if db.get_posting(args.posting_id) is None:
        print(f"log-outcome: unknown posting id {args.posting_id}")
        return 1
    db.log_outcome(args.posting_id, args.status, args.date)
    print(f"log-outcome: {args.posting_id} → {args.status}")
    return 0


def cmd_check_run(args) -> int:
    paths = health.Paths(data_dir=data_dir(), reports_dir=reports_dir(), logs_dir=logs_dir())
    checks = health.run_checks(args.date, paths, digest_recipient(), health.launchd_status())
    print(health.render(args.date, checks))
    return health.exit_code(checks)


def cmd_status(args) -> int:
    criteria = load_criteria()
    db = open_db()
    count = lambda sql: db.conn.execute(sql).fetchone()[0]  # noqa: E731
    print(f"postings stored:   {count('SELECT COUNT(*) FROM postings')}")
    print(f"reported so far:   {count('SELECT COUNT(*) FROM reported')}")
    print(f"last report:       {db.conn.execute('SELECT MAX(run_date) FROM reported').fetchone()[0] or '-'}")
    print(f"outcomes logged:   {count('SELECT COUNT(*) FROM outcomes')}")
    outcomes = [dict(row) for row in db.outcomes_with_scores()]
    print(calibration.Calibrator.from_outcomes(outcomes, args.date, criteria.calibration).note())
    return 0


# --- entry point ----------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobsearch", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, func, help_text):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--date", type=date.fromisoformat, default=date.today(), help="run date (YYYY-MM-DD)")
        p.set_defaults(func=func)
        return p

    add("collect", cmd_collect, "fetch postings from API sources")
    p = add("ingest-discovered", cmd_ingest_discovered, "store postings found by web discovery")
    p.add_argument("--file", type=Path, help="default: every data/batches/<date>/discovered*.json")
    p = add("prepare", cmd_prepare, "dedup, verify, rank; write to_score.json")
    p.add_argument("--dry-run", action="store_true", help="print the exclusion audit only")
    p.add_argument("--no-liveness", action="store_true", help="skip the HTTP liveness check")
    p = add("finalize", cmd_finalize, "validate scores, weight, write the report")
    p.add_argument("--allow-partial", action="store_true", help="write the report even if some scores are invalid")
    p = add("log-outcome", cmd_log_outcome, "record what happened to an application")
    p.add_argument("posting_id")
    p.add_argument("--status", required=True, choices=OUTCOME_STATUSES)
    add("status", cmd_status, "show counts and calibration state")
    add("check-run", cmd_check_run, "check that a day's scheduled run worked (exit 1 on failure)")
    return parser


def main(argv: list[str] | None = None) -> int:
    load_env()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

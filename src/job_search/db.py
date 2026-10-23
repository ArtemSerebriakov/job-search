"""SQLite persistence: postings, verdicts, scores, reported history and outcomes."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import date
from pathlib import Path

from job_search.config import DATA_DIR
from job_search.dedup import fingerprint, normalize_url
from job_search.models import Posting, Verdict

SCHEMA = """
CREATE TABLE IF NOT EXISTS postings (
    id           TEXT PRIMARY KEY,
    norm_url     TEXT NOT NULL UNIQUE,
    fingerprint  TEXT NOT NULL,
    data         TEXT NOT NULL,          -- Posting as JSON
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL,
    closed       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS postings_fp ON postings(fingerprint);

CREATE TABLE IF NOT EXISTS verdicts (
    posting_id TEXT NOT NULL,
    run_date   TEXT NOT NULL,
    rule       TEXT NOT NULL,
    status     TEXT NOT NULL,
    reason     TEXT,
    evidence   TEXT,
    PRIMARY KEY (posting_id, run_date, rule)
);

CREATE TABLE IF NOT EXISTS scores (
    posting_id  TEXT NOT NULL,
    run_date    TEXT NOT NULL,
    data        TEXT NOT NULL,           -- validated ScoreResult as JSON
    final_score REAL NOT NULL,
    PRIMARY KEY (posting_id, run_date)
);

CREATE TABLE IF NOT EXISTS reported (
    posting_id  TEXT NOT NULL,
    run_date    TEXT NOT NULL,
    rank        INTEGER NOT NULL,
    final_score REAL NOT NULL,
    norm_url    TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    PRIMARY KEY (posting_id)
);

CREATE TABLE IF NOT EXISTS outcomes (
    posting_id TEXT PRIMARY KEY,
    status     TEXT NOT NULL,            -- sent | reply | interview | rejected
    sent_on    TEXT,
    updated_on TEXT NOT NULL
);
"""


class DB:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else DATA_DIR / "jobs.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # postings ---------------------------------------------------------------
    def upsert_postings(self, postings: Iterable[Posting], today: date) -> int:
        """Insert new postings, refresh last_seen for known ones. Returns number of new rows."""
        new = 0
        with self.conn:
            for p in postings:
                norm = normalize_url(p.url)
                exists = self.conn.execute(
                    "SELECT 1 FROM postings WHERE norm_url = ?", (norm,)
                ).fetchone()
                if exists:
                    self.conn.execute(
                        "UPDATE postings SET last_seen = ?, data = ? WHERE norm_url = ?",
                        (today.isoformat(), p.model_dump_json(), norm),
                    )
                else:
                    self.conn.execute(
                        "INSERT INTO postings (id, norm_url, fingerprint, data, first_seen, last_seen)"
                        " VALUES (?, ?, ?, ?, ?, ?)",
                        (p.id, norm, fingerprint(p.company, p.title), p.model_dump_json(),
                         today.isoformat(), today.isoformat()),
                    )
                    new += 1
        return new

    def postings_seen_on(self, day: date) -> list[Posting]:
        rows = self.conn.execute("SELECT data FROM postings WHERE last_seen = ?", (day.isoformat(),))
        return [Posting.model_validate_json(r["data"]) for r in rows]

    def get_posting(self, posting_id: str) -> Posting | None:
        row = self.conn.execute("SELECT data FROM postings WHERE id = ?", (posting_id,)).fetchone()
        return Posting.model_validate_json(row["data"]) if row else None

    def mark_closed(self, posting_id: str) -> None:
        with self.conn:
            self.conn.execute("UPDATE postings SET closed = 1 WHERE id = ?", (posting_id,))

    # verdicts ---------------------------------------------------------------
    def save_verdicts(self, posting_id: str, run_date: date, verdicts: list[Verdict]) -> None:
        with self.conn:
            self.conn.executemany(
                "INSERT OR REPLACE INTO verdicts VALUES (?, ?, ?, ?, ?, ?)",
                [(posting_id, run_date.isoformat(), v.rule, v.status, v.reason, v.evidence) for v in verdicts],
            )

    # scores / reported ------------------------------------------------------
    def save_score(self, posting_id: str, run_date: date, data: dict, final_score: float) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO scores VALUES (?, ?, ?, ?)",
                (posting_id, run_date.isoformat(), json.dumps(data), final_score),
            )

    def save_reported(self, run_date: date, ranked: list[tuple[Posting, float]]) -> None:
        """Replace the reported set for `run_date` (re-running finalize for a day is idempotent)."""
        with self.conn:
            self.conn.execute("DELETE FROM reported WHERE run_date = ?", (run_date.isoformat(),))
            for rank, (p, score) in enumerate(ranked, start=1):
                self.conn.execute(
                    "INSERT OR REPLACE INTO reported VALUES (?, ?, ?, ?, ?, ?)",
                    (p.id, run_date.isoformat(), rank, score, normalize_url(p.url),
                     fingerprint(p.company, p.title)),
                )

    def reported_urls(self, before: date) -> set[str]:
        rows = self.conn.execute("SELECT norm_url FROM reported WHERE run_date < ?", (before.isoformat(),))
        return {r["norm_url"] for r in rows}

    def reported_fingerprints(self, before: date) -> dict[str, bool]:
        """fingerprint -> True if the reported posting has since been marked closed."""
        rows = self.conn.execute(
            "SELECT r.fingerprint, p.closed FROM reported r LEFT JOIN postings p ON p.id = r.posting_id"
            " WHERE r.run_date < ?",
            (before.isoformat(),),
        )
        return {r["fingerprint"]: bool(r["closed"]) for r in rows}

    def reported_on(self, day: date) -> list[sqlite3.Row]:
        return list(self.conn.execute(
            "SELECT * FROM reported WHERE run_date = ? ORDER BY rank", (day.isoformat(),)
        ))

    # outcomes ---------------------------------------------------------------
    def log_outcome(self, posting_id: str, status: str, today: date) -> None:
        with self.conn:
            existing = self.conn.execute(
                "SELECT sent_on FROM outcomes WHERE posting_id = ?", (posting_id,)
            ).fetchone()
            sent_on = existing["sent_on"] if existing else today.isoformat()
            self.conn.execute(
                "INSERT OR REPLACE INTO outcomes VALUES (?, ?, ?, ?)",
                (posting_id, status, sent_on, today.isoformat()),
            )

    def outcomes_with_scores(self) -> list[sqlite3.Row]:
        """Each logged application joined with the score it had when it was reported."""
        return list(self.conn.execute(
            "SELECT o.posting_id, o.status, o.sent_on, o.updated_on, r.final_score"
            " FROM outcomes o JOIN reported r ON r.posting_id = o.posting_id"
        ))

    def daily_chances(self, since: date) -> list[sqlite3.Row]:
        return list(self.conn.execute(
            "SELECT run_date, final_score, rank FROM reported WHERE run_date >= ? ORDER BY run_date, rank",
            (since.isoformat(),),
        ))

"""Markdown digest. The URLs in it are exactly the reported postings: the next day's dedup reads
every URL in earlier reports, so excluded postings are listed by title only, never by link."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from job_search.dedup import REPORT_GLOB
from job_search.models import Posting, Verdict, source_label
from job_search.scoring import ScoreResult

# Plain-language names for the exclusion table.
RULE_LABELS = {
    "dedup": "Already reported on an earlier day",
    "link": "No direct link to the posting",
    "location": "Outside Germany / Netherlands / UAE",
    "enrollment": "Student, intern or thesis role",
    "seniority": "Too senior (title, or more than 2 years required)",
    "description_language": "Not written in English or Russian",
    "language": "Requires fluent German (or another local language)",
    "liveness": "Posting closed or removed",
    "same-day duplicate": "Same role listed twice today",
    "llm_crosscheck": "Failed the fact check against the posting",
    "below score threshold": "Too weak a match (below the score threshold)",
}

_LABELS = {"genai_relevance": "GenAI", "skills_match": "Skills", "seniority_fit": "Seniority",
           "domain_fit": "Domain", "growth": "Growth"}


@dataclass
class Entry:
    posting: Posting
    score: float
    result: ScoreResult
    flags: list[Verdict] = field(default_factory=list)


@dataclass
class Funnel:
    collected: int
    new: int
    passed: int
    scored: int
    reported: int


def report_path(reports_dir: Path, day: date) -> Path:
    return reports_dir / REPORT_GLOB.replace("*", day.isoformat())


def render(day: date, entries: list[Entry], digest_size: int, chance: float, chance_avg: float | None,
           calibration_note: str, funnel: Funnel, audit: dict[str, list[str]], problems: list[str]) -> str:
    lines = [f"# Job digest {day.isoformat()}", ""]
    avg = f" (7-day avg {chance_avg * 100:.0f})" if chance_avg is not None else ""
    lines += [f"**Chance today: {chance * 100:.0f}/100**{avg} — odds of at least one human reply if you "
              f"apply to the best 3 below.", f"_{calibration_note}_", ""]

    if not entries:
        lines += ["No new postings passed every filter today.", ""]
    elif len(entries) < digest_size:
        lines += [f"{len(entries)} new roles today — fewer than {digest_size}, because no more new postings "
                  f"passed every filter and the score threshold. The list is not padded.", ""]
    else:
        lines += [f"{len(entries)} new roles today.", ""]

    for i, e in enumerate(entries, start=1):
        p = e.posting
        where = p.location or "location not stated"
        lines += [f"## {i}. [{p.title}]({p.url}) — {e.score:.0f}",
                  f"{p.company} · {where} · via {source_label(p.source)}",
                  "Sub-scores: " + " · ".join(f"{_LABELS[k]} {v}" for k, v in e.result.sub_scores.model_dump().items())]
        for flag in e.flags:
            lines.append(f"- ⚠ {flag.reason}")
        if e.result.rationale:
            lines.append(f"Why: {e.result.rationale}")
        lines += [f"ID `{p.id}`", ""]

    if entries:
        lines += ["After applying, log it so the score can be calibrated: "
                  "`uv run jobsearch log-outcome <ID> --status sent`", ""]
    lines += ["---", "## Funnel",
              f"collected today {funnel.collected} → new {funnel.new} → passed filters {funnel.passed} → "
              f"scored {funnel.scored} → reported {funnel.reported}", ""]
    if audit:
        lines += ["## Excluded today", "| Rule | Count | Examples |", "|---|---|---|"]
        for rule, examples in sorted(audit.items(), key=lambda kv: -len(kv[1])):
            sample = "; ".join(x.replace("|", "/") for x in examples[:2])
            lines.append(f"| {RULE_LABELS.get(rule, rule)} | {len(examples)} | {sample} |")
        lines.append("")
    if problems:
        lines += ["## Scoring problems", *[f"- {p}" for p in problems], ""]
    return "\n".join(lines)


def write(reports_dir: Path, day: date, content: str) -> Path:
    path = report_path(reports_dir, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


# --- email formats --------------------------------------------------------------------------------
# The report uses a small, fixed subset of Markdown, so a dedicated converter is simpler and more
# predictable than a dependency.

_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![\w*])_(.+?)_(?![\w*])")
_CODE = re.compile(r"`([^`]+)`")


def _inline_html(text: str) -> str:
    text = html.escape(text, quote=False)
    text = _LINK.sub(lambda m: f'<a href="{html.escape(m.group(2))}">{m.group(1)}</a>', text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    return _CODE.sub(r"<code>\1</code>", text)


def to_html(markdown: str) -> str:
    out: list[str] = ['<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
                      'font-size:14px;line-height:1.45;color:#1a1a1a;max-width:760px">']
    in_list = in_table = False
    for line in markdown.splitlines():
        if in_list and not line.startswith("- "):
            out.append("</ul>")
            in_list = False
        if in_table and not line.startswith("|"):
            out.append("</table>")
            in_table = False
        if line.startswith("# "):
            out.append(f"<h1>{_inline_html(line[2:])}</h1>")
        elif line.startswith("## "):
            out.append(f'<h2 style="font-size:16px;margin:18px 0 4px">{_inline_html(line[3:])}</h2>')
        elif line.startswith("- "):
            if not in_list:
                out.append('<ul style="margin:2px 0;padding-left:18px">')
                in_list = True
            out.append(f"<li>{_inline_html(line[2:])}</li>")
        elif line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= {"-"} for c in cells):
                continue
            if not in_table:
                out.append('<table style="border-collapse:collapse;font-size:13px" cellpadding="4" border="1">')
                in_table = True
                out.append("<tr>" + "".join(f"<th>{_inline_html(c)}</th>" for c in cells) + "</tr>")
            else:
                out.append("<tr>" + "".join(f"<td>{_inline_html(c)}</td>" for c in cells) + "</tr>")
        elif line.strip() == "---":
            out.append("<hr>")
        elif line.strip():
            out.append(f'<p style="margin:2px 0">{_inline_html(line)}</p>')
    if in_list:
        out.append("</ul>")
    if in_table:
        out.append("</table>")
    out.append("</div>")
    return "\n".join(out)


def to_plain_text(markdown: str) -> str:
    text = _LINK.sub(r"\1 — \2", markdown)
    text = _BOLD.sub(r"\1", text)
    text = _ITALIC.sub(r"\1", text)
    text = _CODE.sub(r"\1", text)
    text = re.sub(r"^#+ ", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\|[-| ]+\|$\n?", "", text, flags=re.MULTILINE)
    return re.sub(r"^\| (.*) \|$", lambda m: m.group(1).replace(" | ", " — "), text, flags=re.MULTILINE)


def write_email(batch_dir: Path, markdown: str) -> tuple[Path, Path]:
    """email.html and email.txt for the Gmail step (kept out of reports/, which dedup reads)."""
    batch_dir.mkdir(parents=True, exist_ok=True)
    html_path, text_path = batch_dir / "email.html", batch_dir / "email.txt"
    html_path.write_text(to_html(markdown))
    text_path.write_text(to_plain_text(markdown))
    return html_path, text_path

# Verification (hard filters)

Location: `src/job_search/verify/`. Each rule is a pure function returning
`Verdict(status=pass|fail|flag, rule, reason, evidence)`.
`pipeline.verify()` runs dedup and then the static rules, cheapest first, stopping at the first
FAIL. Liveness runs last, and only when an HTTP client is passed. A FAIL excludes the posting;
a FLAG keeps it and shows a warning in the report.

| Rule | Module | Fails when | Flags when |
|---|---|---|---|
| dedup | `dedup.py` | normalised URL already reported (DB or `reports/*.md`); repost (same company + normalised title) at a new URL | repost of a role that had closed (reopened) |
| link | `link.py` | no URL, search engine, LinkedIn non-`/jobs/view/`, search-results query, careers listing page, article/blog | — |
| location | `location.py` | not a named company AND (recognised place outside DE/NL/AE, or remote restricted to other countries) | location unstated/unrecognised; remote within EMEA/EU/worldwide |
| enrollment | `enrollment.py` | Werkstudent/working student/intern/Praktikum/thesis/dual study/"student" in title; enrollment required in body | — |
| seniority | `seniority.py` | senior/lead/staff/principal/head/manager/mid/middle/II/III/…leiter/…leitung/co-founder/CxO in title; "senior-level" / "experience as a senior" required in body; required years > `max_min_years` (2); "Associate" in consulting/banking/law without a stated years requirement | no entry-level marker and no years stated |
| description_language | `description_language.py` | description written in any language other than English or Russian (Cyrillic/Arabic by script; Latin languages by exclusive function words; bilingual passes if ≥ 40% of function words are English) | description empty or too short to tell |
| language | `language.py` | German/Dutch/Arabic at fluent/B2+ level, or "German required", unless English is the stated working language | — |
| same-day duplicate | `dedup.collapse_duplicates` | same company + normalised title already passing today (keeps employer listing, then longest text) | — |
| llm_crosscheck | `scoring.cross_check` (in `finalize`) | model-extracted fact violates a criterion (years > 2, enrollment, German B2+ without English working language) AND its quote is found verbatim in the posting | same claim but quote not found in the posting |
| liveness | `liveness.py` | HTTP 404/410, closed-phrase on page, redirect to a listing page | 401/403/429/5xx/network error; live only on an aggregator |

Sentence splitting (`verify/text.py`) first removes abbreviation periods (e.g., i.e., z.B., ca., etc.)
so "Experience with LLMs (e.g. GPT-4) for 3+ years" stays one sentence (leak fixed 2026-10-30).

Years extraction (`seniority.required_years`): per sentence the minimum number counts (alternatives);
across sentences the maximum counts; nice-to-have sentences and non-requirement sentences
("founded 10 years ago", "30 days vacation") are skipped; vague multi-year phrases
("mehrjährige", "several years") count as 3.

## How to change a rule
- Use the `/fix-leak` skill. A leak is fixed **in code with a regression test**, never by
  tweaking the scoring prompt. A prompt is a request; a tested function is a guarantee.
- Add the offending snippet to the rule's test file first, watch it fail, then fix.
- Add a passing case for the nearest legitimate phrasing to guard against false positives.
- Keep German and English patterns side by side.

---
name: fix-leak
description: Fix a verification leak — a posting that reached the digest but should have been excluded (Werkstudent, too senior, German required, description not in English/Russian, wrong country, closed, duplicate), or a good posting that was wrongly excluded. Use when the user reports a wrong posting in a report.
---

# Fix a leak (or a false rejection)

A prompt is a request; a tested function is a guarantee. Leaks are fixed in `src/job_search/verify/`,
never in the scoring prompt.

1. **Identify the posting.** Get its URL/title from the report and its text from `data/jobs.db`
   (`postings.data`) or the live page. Find which rule should have caught it
   (see `.claude/rules/verification.md`) and which verdict it actually got (`verdicts` table).
2. **Write the failing test first.** Add the smallest real snippet (title or sentence) to that
   rule's test file in `tests/test_verify_<rule>.py`, as a new parametrize case.
   Run `uv run pytest tests/test_verify_<rule>.py -q` and confirm it fails for the expected reason.
3. **Fix the rule** with the narrowest change that makes the test pass. Keep English and German
   patterns side by side. Watch for false positives: add a passing case for the nearest legitimate
   phrasing (e.g. "German is a plus" when tightening the German rule).
4. **Run the full suite**: `uv run pytest`. All tests must pass. Explain to the user any test that
   failed before changing anything else.
5. **Update docs** if the rule's behaviour changed: the table in `.claude/rules/verification.md`.
6. Suggest a commit message (`Fix <rule> leak: <short description>`); don't commit without a yes.

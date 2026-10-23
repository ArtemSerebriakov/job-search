# Search criteria (from the user — source of truth)

The candidate's CV is in `config/profile.md` (local, git-ignored; template:
`config/profile.example.md`). In short: a recent MSc graduate with ~1.5 years of AI engineering
experience (LLM agents, RAG). Target: Graduate/Junior/Associate/early-career (0–2 years) in AI Eng,
ML Eng, NLP Eng, Data Science, Applied/Research Science. GenAI/LLM/NLP roles preferred.
Never copy CV details into tracked files.

## Location
- Named companies (`config/criteria.yaml: named_companies`): any country, any work mode.
- Everyone else: Germany > Netherlands > UAE only. Munich is the top priority.

## Hard requirements
- Seniority 0–2 years. "Associate" in consulting/banking/law needs explicit ≤ 2 years.
  Unstated seniority → include but flag.
- No Werkstudent / working-student / roles requiring university enrollment.
- Open posting, verified on the original source; aggregator-only → say so explicitly.
- Direct link to the posting itself.
- Description must be written in English or Russian (bilingual with a full English part is fine).
- No German (or other local language) fluency requirement unless English is the working language.
- Sponsorship is NOT checked or reported (user's decision).

## Dedup
- Exclude any URL already reported in `reports/job-search_daily-reports_*.md`.
- Reposts at a new URL are skipped unless the role reopened after being closed.

## Output
Up to 10 new candidates per day; fewer if not enough pass, stated plainly, never padded.

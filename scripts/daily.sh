#!/bin/bash
# Daily headless run, started by launchd at 08:00 (launchd/com.job-search.daily.plist).
# launchd starts with an almost empty environment, so PATH is set explicitly.
set -euo pipefail

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT"
mkdir -p logs
LOG="logs/$(date +%F).log"

ALLOWED_TOOLS=(
  "Bash(uv run jobsearch *)"
  "Read"
  "Edit(./data/batches/**)"
  "WebSearch"
  "WebFetch"
  "Task"
  "Agent"
  # job connectors: read-only search and detail tools only
  "mcp__claude_ai_Indeed__search_jobs"
  "mcp__claude_ai_Indeed__get_job_details"
  "mcp__claude_ai_JobDataLake__search_jobs"
  "mcp__claude_ai_JobDataLake__get_job"
  "mcp__claude_ai_JobDataLake__get_filter_options"
  "mcp__claude_ai_Jobs_by_Workable__search_jobs"
  "mcp__claude_ai_Jobs_by_Workable__get_job"
  "mcp__claude_ai_Gmail__send_message"
  "mcp__claude_ai_Gmail__create_draft"
)

status=0
{
  echo "=== $(date) daily digest start"
  claude -p "/daily-digest" --model sonnet --allowedTools "${ALLOWED_TOOLS[@]}" || status=$?
  echo "=== $(date) daily digest end (exit $status)"
} >> "$LOG" 2>&1
exit "$status"

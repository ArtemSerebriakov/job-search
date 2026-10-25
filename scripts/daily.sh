#!/bin/bash
# Daily headless run, started by launchd at 08:00 (launchd/com.job-search.daily.plist).
# launchd starts with an almost empty environment, so PATH is set explicitly.
set -euo pipefail

notify() {  # macOS notification; works without Claude or Gmail
  /usr/bin/osascript -e "display notification \"$1\" with title \"Job digest\" sound name \"Basso\"" || true
}

trap 'notify "The morning run could not start: see logs/launchd.err.log"' ERR

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT"
mkdir -p logs
LOG="logs/$(date +%F).log"

# Headless Claude stops background agents 10 minutes after its last turn by default; discovery
# takes longer (2026-10-25 run was cut off). Allow 45 minutes, not forever, so a hung agent ends.
export CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=2700000

# After wake the network (and with it the claude.ai connectors) can take a while to come up
# (2026-10-25 08:01: sources and connectors failed). Wait up to 5 minutes for it.
for _ in $(seq 1 30); do
  /usr/bin/curl -s -o /dev/null -m 5 https://api.anthropic.com && break
  /bin/sleep 10
done

ALLOWED_TOOLS=(
  "Bash(uv run jobsearch *)"
  "Read"
  "Edit(./data/batches/**)"
  "WebSearch"
  "WebFetch"
  "Task"
  "Agent"
  "ToolSearch"
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
  echo "=== $(date) health check"
  uv run jobsearch check-run || check_status=$?
} >> "$LOG" 2>&1

if [ "$status" -ne 0 ]; then
  notify "The morning run failed (exit $status). See logs/$(date +%F).log"
elif [ "${check_status:-0}" -ne 0 ]; then
  notify "The morning run finished with problems. Run /check-run or see logs/$(date +%F).log"
fi
exit "$status"

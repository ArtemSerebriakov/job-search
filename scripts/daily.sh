#!/bin/bash
# Daily headless run, started by launchd at 08:00 with catch-ups at 11/14/17 (launchd/com.job-search.daily.plist).
# launchd starts with an almost empty environment, so PATH is set explicitly.
set -euo pipefail

notify() {  # macOS notification; works without Claude or Gmail
  /usr/bin/osascript -e "display notification \"$1\" with title \"Job digest\" sound name \"Basso\"" || true
}

trap 'notify "The job digest run could not start: see logs/launchd.err.log"' ERR

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT"
mkdir -p logs
DAY="$(date +%F)"
LOG="logs/$DAY.log"
BATCH="data/batches/$DAY"
REPORT="reports/job-search_daily-reports_$DAY.md"

# Catch-up runs: launchd starts this at 08:00, 11:00, 14:00 and 17:00 (on the next wake if asleep).
# With the lid closed on battery macOS keeps the Mac asleep apart from a few seconds of dark wake, so
# the 08:00 run can die mid-way (2026-11-13). Later starts exit here once the day is done.
LAST_ATTEMPT_HOUR=17  # keep in sync with StartCalendarInterval in launchd/com.job-search.daily.plist.template
is_last_attempt() { [ "$(date +%H)" -ge "$LAST_ATTEMPT_HOUR" ]; }

if [ -f "$BATCH/email_sent.json" ]; then
  exit 0  # today's digest was already sent
fi
if [ -f "$REPORT" ]; then
  # Report written but not emailed (e.g. only a draft). Rerunning would spend JobsPipe credits again
  # and dedup would drop the postings already in that report, so stop and tell the user once.
  if [ ! -f "$BATCH/.unsent-notified" ]; then
    echo "=== $(date) report exists but email_sent.json is missing; not rerunning" >> "$LOG"
    notify "Today's report was written but not emailed. See $REPORT"
    mkdir -p "$BATCH" && touch "$BATCH/.unsent-notified"
  fi
  exit 0
fi

# Headless Claude stops background agents 10 minutes after its last turn by default; discovery
# takes longer (2026-10-25 run was cut off). Allow 45 minutes, not forever, so a hung agent ends.
export CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=2700000

# After wake the network (and with it the claude.ai connectors) can take a while to come up
# (2026-10-25 08:01: sources and connectors failed). Wait up to 5 minutes for it; if it never comes
# up, skip without starting Claude and leave it to the next catch-up run.
online=false
deadline=$((SECONDS + 300))
while :; do  # always one more try after waking: SECONDS is wall-clock and keeps counting in sleep
  if /usr/bin/curl -s -o /dev/null -m 5 https://api.anthropic.com; then online=true; break; fi
  [ "$SECONDS" -ge "$deadline" ] && break
  /bin/sleep 10
done
if ! $online; then
  echo "=== $(date) no network after 5 minutes (Mac asleep or offline); skipped" >> "$LOG"
  if is_last_attempt; then
    notify "No internet for today's last attempt; nothing was sent. Rerun by hand when online."
  fi
  exit 0
fi
if [ "$(date +%F)" != "$DAY" ]; then
  echo "=== $(date) the Mac slept through midnight during the network wait; skipped" >> "$LOG"
  exit 0  # that day's catch-ups are over
fi

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
  # careers-browser: headless isolated browser from config/browser-mcp.json
  "mcp__careers-browser__browser_navigate"
  "mcp__careers-browser__browser_wait_for"
  "mcp__careers-browser__browser_evaluate"
  "mcp__careers-browser__browser_close"
  "mcp__claude_ai_Gmail__send_message"
  "mcp__claude_ai_Gmail__create_draft"
)

status=0
{
  echo "=== $(date) daily digest start"
  # caffeinate: no idle sleep during the run (and no system sleep on AC power). It cannot stop
  # the forced sleep of a closed lid on battery; the catch-up runs cover that.
  /usr/bin/caffeinate -is claude -p "/daily-digest" --model sonnet --mcp-config config/browser-mcp.json \
    --allowedTools "${ALLOWED_TOOLS[@]}" || status=$?
  echo "=== $(date) daily digest end (exit $status)"
  echo "=== $(date) health check"
  uv run jobsearch check-run --date "$DAY" || check_status=$?
} >> "$LOG" 2>&1

if [ "$status" -ne 0 ]; then
  if is_last_attempt; then
    notify "Today's last run failed (exit $status); nothing was sent. See $LOG"
  else
    notify "The run failed (exit $status); it retries at the next catch-up time. See $LOG"
  fi
elif [ "${check_status:-0}" -ne 0 ]; then
  notify "The run finished with problems. Run /check-run or see $LOG"
fi
exit "$status"

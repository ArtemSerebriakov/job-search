#!/bin/bash
# Daily headless run. launchd starts it every 30 minutes; it only runs between 08:00 and 22:00,
# with the lid open or on power, until today's digest is sent (launchd/com.job-search.daily.plist).
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

# Starts every 30 minutes (launchd StartInterval; a start missed while asleep runs on the next wake).
# With the lid closed on battery macOS only dark-wakes for seconds, so a run started then dies offline
# (2026-11-13, 2026-11-14). Those starts are skipped; the first start after the lid opens does the run.
FIRST_HOUR=8      # no runs before 08:00 ...
LAST_HOUR=22      # ... or from 22:00
MAX_ATTEMPTS=3    # real attempts (Claude started) per day, so a failing run can't burn credits all day
hour=$((10#$(date +%H)))

# Log a skip and exit. Silent unless it's the last hour of the window and no digest went out today.
skip() {
  local last
  last="$(tail -n 1 "$LOG" 2>/dev/null || true)"
  [[ "$last" == *"$1; skipped" ]] || echo "=== $(date) $1; skipped" >> "$LOG"  # no repeated lines
  if [ "$hour" -ge $((LAST_HOUR - 1)) ] && [ ! -f "$BATCH/.no-digest-notified" ]; then
    notify "No job digest today ($1). Run /check-run or rerun by hand."
    mkdir -p "$BATCH" && touch "$BATCH/.no-digest-notified"
  fi
  exit 0
}

lid_closed_on_battery() {
  local lid power
  lid="$(/usr/sbin/ioreg -r -k AppleClamshellState -d 4 2>/dev/null || true)"
  power="$(/usr/bin/pmset -g batt 2>/dev/null || true)"
  [[ "$lid" == *'"AppleClamshellState" = Yes'* && "$power" == *"'Battery Power'"* ]]
}

if [ "$hour" -lt "$FIRST_HOUR" ] || [ "$hour" -ge "$LAST_HOUR" ]; then
  exit 0  # outside the daily window
fi
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
attempts="$(grep -c -E '^=== .*daily digest start$' "$LOG" 2>/dev/null || true)"
attempts="${attempts:-0}"
if [ "$attempts" -ge "$MAX_ATTEMPTS" ]; then
  skip "attempt limit ($MAX_ATTEMPTS) reached"
fi
if lid_closed_on_battery; then
  skip "lid closed on battery (dark wake)"
fi

# Headless Claude stops background agents 10 minutes after its last turn by default; discovery
# takes longer (2026-10-25 run was cut off). Allow 45 minutes, not forever, so a hung agent ends.
export CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=2700000

# After wake the network (and with it the claude.ai connectors) can take a while to come up
# (2026-10-25 08:01: sources and connectors failed). Wait up to 5 minutes for it; if it never comes
# up, skip without starting Claude and leave it to the next start.
online=false
deadline=$((SECONDS + 300))
while :; do  # always one more try after waking: SECONDS is wall-clock and keeps counting in sleep
  if /usr/bin/curl -s -o /dev/null -m 5 https://api.anthropic.com; then online=true; break; fi
  [ "$SECONDS" -ge "$deadline" ] && break
  /bin/sleep 10
done
if ! $online; then
  skip "no network after 5 minutes (Mac asleep or offline)"
fi
if [ "$(date +%F)" != "$DAY" ]; then
  echo "=== $(date) the Mac slept through midnight during the network wait; skipped" >> "$LOG"
  exit 0  # that day is over
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
  # the forced sleep of a closed lid on battery; the lid check and the next 30-min start cover that.
  /usr/bin/caffeinate -is claude -p "/daily-digest" --model sonnet --mcp-config config/browser-mcp.json \
    --allowedTools "${ALLOWED_TOOLS[@]}" || status=$?
  echo "=== $(date) daily digest end (exit $status)"
  echo "=== $(date) health check"
  uv run jobsearch check-run --date "$DAY" || check_status=$?
} >> "$LOG" 2>&1

if [ "$status" -ne 0 ]; then
  if [ $((attempts + 1)) -ge "$MAX_ATTEMPTS" ] || [ "$((10#$(date +%H)))" -ge $((LAST_HOUR - 1)) ]; then
    notify "Today's last run failed (exit $status); nothing was sent. See $LOG"
  else
    notify "The run failed (exit $status); it retries within 30 minutes. See $LOG"
  fi
elif [ "${check_status:-0}" -ne 0 ]; then
  notify "The run finished with problems. Run /check-run or see $LOG"
fi
exit "$status"

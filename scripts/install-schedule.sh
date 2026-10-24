#!/bin/bash
# Install (or reinstall) the 08:00 schedule for this checkout.
#
#   scripts/install-schedule.sh            build the runner app if missing, install the launchd job
#   scripts/install-schedule.sh --check    also run a harmless permission check now (approve the
#                                           macOS "Desktop folder" prompt when it appears)
#   scripts/install-schedule.sh --rebuild-runner   rebuild the app (macOS will ask for permission again)
set -euo pipefail

PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.job-search.daily"
RUNNER="$HOME/Applications/JobSearchRunner.app"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"
CHECK=false; REBUILD=false
for arg in "$@"; do
  case "$arg" in
    --check) CHECK=true ;;
    --rebuild-runner) REBUILD=true ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

mkdir -p "$HOME/Applications" "$HOME/Library/LaunchAgents" "$PROJECT/logs"

# The runner app lives outside ~/Desktop so launchd can open it. Rebuilding changes its signature,
# which makes macOS forget the Desktop permission, so it is only rebuilt when missing or asked.
if [ ! -d "$RUNNER" ] || $REBUILD; then
  rm -rf "$RUNNER"
  sed "s#__PROJECT_DIR__#$PROJECT#g" "$PROJECT/launchd/JobSearchRunner.applescript.template" \
    | osacompile -o "$RUNNER"
  /usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$RUNNER/Contents/Info.plist"  # no Dock icon
  /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier com.job-search.runner" "$RUNNER/Contents/Info.plist" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string com.job-search.runner" "$RUNNER/Contents/Info.plist"
  codesign --force --deep --sign - "$RUNNER"
  echo "Built $RUNNER"
fi

sed -e "s#__PROJECT_DIR__#$PROJECT#g" -e "s#__RUNNER_APP__#$RUNNER#g" \
  "$PROJECT/launchd/$LABEL.plist.template" > "$TARGET"
plutil -lint "$TARGET" >/dev/null
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"
echo "Installed $LABEL (daily 08:00) -> $TARGET"

if $CHECK; then
  touch "$HOME/.job-search-permission-check"
  rm -f "$PROJECT/logs/permission-check.log"
  echo "Running the permission check. If macOS asks whether JobSearchRunner may access your"
  echo "Desktop folder, click Allow."
  /usr/bin/open -W -g -a "$RUNNER"
  if [ -s "$PROJECT/logs/permission-check.log" ]; then
    cat "$PROJECT/logs/permission-check.log"
  else
    echo "No check log: access was denied or the prompt is still open." >&2
    exit 1
  fi
fi

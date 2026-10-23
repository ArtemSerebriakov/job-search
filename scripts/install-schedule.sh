#!/bin/bash
# Install (or reinstall) the 08:00 launchd job for this checkout.
# Renders launchd/com.job-search.daily.plist.template with this project's path.
set -euo pipefail

PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.job-search.daily"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT/logs"
sed "s#__PROJECT_DIR__#$PROJECT#g" "$PROJECT/launchd/$LABEL.plist.template" > "$TARGET"
plutil -lint "$TARGET" >/dev/null
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"
echo "Installed $LABEL (daily 08:00) -> $TARGET"

#!/usr/bin/env bash
# Adds a nightly cron entry (default 1:30 AM). Usage: ./scripts/install_schedule_mac_linux.sh [HH] [MM]
# Remove later with:  crontab -l | grep -v photobooth_studio_overnight | crontab -
set -e
HOUR="${1:-1}"; MIN="${2:-30}"
DIR="$(cd "$(dirname "$0")/.." && pwd)"
chmod +x "$DIR/scripts/run_overnight.sh"
LINE="$MIN $HOUR * * * \"$DIR/scripts/run_overnight.sh\" # photobooth_studio_overnight"
( crontab -l 2>/dev/null | grep -v photobooth_studio_overnight; echo "$LINE" ) | crontab -
echo "Installed nightly run at $(printf %02d:%02d "$HOUR" "$MIN"):"
echo "  $LINE"
echo "Your computer must be on (not asleep) at that time. Logs: $DIR/output/logs/"

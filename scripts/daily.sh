#!/usr/bin/env bash
# Daily outreach run. Intended for cron on a machine that has the .env and the
# cached Google token.
#
#   30 8 * * 1-5  cd /path/to/vending-outreach-automation && ./scripts/daily.sh
#
# MODE defaults to `draft`, which stages everything in Gmail for Steven to skim
# and hit send on. Set MODE=live once the copy has earned that trust.
set -euo pipefail

cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
MODE=${MODE:-draft}
LOG_DIR=data/logs
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/$(date +%Y-%m-%d).log"

# `daily` runs the whole pass and keeps going if one stage fails.
"$PY" main.py daily --mode "$MODE" 2>&1 | tee -a "$LOG"

echo "Done. Log: $LOG"

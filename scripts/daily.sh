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
export PYTHONPATH=src
PY=${PYTHON:-python3}
MODE=${MODE:-draft}
LOG_DIR=data/logs
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/$(date +%Y-%m-%d).log"

run() {
  echo "--- $* ---" | tee -a "$LOG"
  "$PY" -m vending_outreach "$@" 2>&1 | tee -a "$LOG"
}

# Widen the top of the funnel a little each day rather than all at once, so the
# Places bill and the crawl load stay predictable.
run discover
run enrich --limit 150
run score
run queue --limit 60
run outreach --mode "$MODE" --limit 40
run sync --limit 40
run report

echo "Done. Log: $LOG"

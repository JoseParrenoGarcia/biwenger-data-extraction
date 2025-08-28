#!/usr/bin/env bash
set -euo pipefail

# Go to repo root (folder above this script)
cd "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")"/.. && pwd)"
export PYTHONPATH="$PWD"

notify() {
  # Works if you're logged into macOS; safely no-ops elsewhere
  if command -v osascript >/dev/null 2>&1; then
    osascript -e "display notification \"$1\" with title \"Biwenger Cron\""
  fi
}

notify "Scraping started…"

if python3 scraping_biwenger/runner.py "$@"; then
  notify "Scraping completed successfully."
else
  notify "Scraping failed ❌. Check logs."
  exit 1
fi

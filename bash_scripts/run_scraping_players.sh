# ~/bin/run_scraping_players.sh
#!/usr/bin/env bash
set -euo pipefail

# --- Stable env for launchd ---
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"

# --- Your repo ---
REPO="/Users/joseparreno/Documents/GitHub/biwenger-data-extraction"
cd "$REPO" || exit 90
export PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}"

# --- Prefer project venv; fallback to system python ---
PY="$REPO/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PY="$(command -v python3)"
  else
    PY="/usr/bin/python3"
  fi
fi

# --- macOS Notification helper ---
notify() {
  if command -v osascript >/dev/null 2>&1; then
    /usr/bin/osascript -e 'display notification "'"$1"'" with title "Biwenger Cron"'
  fi
}

notify "Players scraping started…"

# --- Run your scraper (module exec + required subcommand) ---
code1=0
if "$PY" "$REPO/scraping_biwenger/runner.py" "$@"; then
  notify "Players scraping ✅ completed."
else
  code1=$?
  notify "Players scraping ❌ failed (exit $code1)."
fi

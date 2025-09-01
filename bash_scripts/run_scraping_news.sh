# ~/bin/run_scraping_news.sh
#!/usr/bin/env bash
set -euo pipefail

# ---- Stable env for launchd ----
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"

# ---- Your repo ----
REPO="/Users/joseparreno/Documents/GitHub/biwenger-data-extraction"
cd "$REPO" || exit 90
export PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}"

# ---- Prefer project venv; fallback to system python ----
PY="$REPO/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PY="$(command -v python3)"
  else
    PY="/usr/bin/python3"
  fi
fi

# ---- macOS Notification helper ----
notify() {
  if command -v osascript >/dev/null 2>&1; then
    /usr/bin/osascript -e 'display notification "'"$1"'" with title "Biwenger Cron"'
  fi
}

notify "News scraping started…"

# ---- 1) Run scraping_news ----
code1=0
if "$PY" "$REPO/scraping_news/runner.py" "$@"; then
  notify "News scraping ✅ completed."
else
  code1=$?
  notify "News scraping ❌ failed (exit $code1)."
fi

# ---- 2) Run structured_news regardless of step 1 ----
code2=0
if "$PY" "$REPO/structured_news/runner.py" "$@"; then
  notify "Structured news generation ✅ completed."
else
  code2=$?
  notify "Structured news generation ❌ failed (exit $code2)."
fi

# ---- Final summary and exit code ----
if (( code1 == 0 && code2 == 0 )); then
  notify "All news jobs ✅✅ done."
  exit 0
else
  notify "Some jobs failed: scraping=$code1, structured=$code2."
  # Exit non-zero so launchd knows it was not all sunshine.
  exit 1
fi

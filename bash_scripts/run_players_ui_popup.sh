#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="$REPO_ROOT/.venv/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Expected virtualenv python at $PYTHON_BIN"
  echo "Create the project venv before using the popup launcher."
  exit 1
fi

if [[ $# -gt 0 ]]; then
  RUN_ARGS="$*"
else
  RUN_ARGS="--headed --dry-run --terminal-ui --max-player-pages 1 --max-players 2"
fi

COMMAND="cd $REPO_ROOT && $PYTHON_BIN -m scraping_biwenger.get_player_stats $RUN_ARGS"

/usr/bin/osascript <<EOF
tell application "Terminal"
  activate
  do script "$COMMAND"
end tell
EOF

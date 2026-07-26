#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/biwenger_job_lib.sh"

biwenger_prepare_env
REPO_ROOT="$(biwenger_repo_root)"
cd "$REPO_ROOT"
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

RETENTION_DAYS="${BIWENGER_RUN_RETENTION_DAYS:-7}"
biwenger_start_log "$REPO_ROOT" "current_team" "$RETENTION_DAYS"

PY="$(biwenger_python "$REPO_ROOT")"

args=(
  -m scraping_biwenger.get_current_team
  --headed
)

if [[ "${BIWENGER_DRY_RUN:-0}" == "1" ]]; then
  args+=(--dry-run)
fi

args+=("$@")

echo "Repo: $REPO_ROOT"
echo "Python: $PY"
echo "Command: $PY ${args[*]}"

biwenger_notify "Biwenger Current Team" "Current-team scraping started."

if "$PY" "${args[@]}"; then
  echo "Completed at: $(date)"
  biwenger_notify "Biwenger Current Team" "Current-team scraping completed."
  exit 0
else
  code=$?
  echo "Failed at: $(date)"
  echo "Exit code: $code"
  biwenger_notify "Biwenger Current Team" "Current-team scraping failed with exit code $code."
  exit "$code"
fi

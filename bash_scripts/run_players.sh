#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/biwenger_job_lib.sh"

biwenger_prepare_env
REPO_ROOT="$(biwenger_repo_root)"
cd "$REPO_ROOT"
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

RETENTION_DAYS="${BIWENGER_RUN_RETENTION_DAYS:-7}"
biwenger_start_log "$REPO_ROOT" "players" "$RETENTION_DAYS"

PY="$(biwenger_python "$REPO_ROOT")"

args=(
  -m scraping_biwenger.get_player_stats
  --headed
  --upload-batch-size "${BIWENGER_UPLOAD_BATCH_SIZE:-10}"
  --retry-top-players "${BIWENGER_RETRY_TOP_PLAYERS:-400}"
  --run-retention-days "$RETENTION_DAYS"
)

if [[ -n "${BIWENGER_MAX_PLAYER_PAGES:-}" ]]; then
  args+=(--max-player-pages "$BIWENGER_MAX_PLAYER_PAGES")
fi

if [[ -n "${BIWENGER_MAX_PLAYERS:-}" ]]; then
  args+=(--max-players "$BIWENGER_MAX_PLAYERS")
fi

if [[ -n "${BIWENGER_PLAYER_SLUG:-}" ]]; then
  args+=(--player-slug "$BIWENGER_PLAYER_SLUG")
fi

if [[ -n "${BIWENGER_RESUME_CHECKPOINT:-}" ]]; then
  args+=(--resume-checkpoint "$BIWENGER_RESUME_CHECKPOINT")
fi

if [[ "${BIWENGER_DRY_RUN:-0}" == "1" ]]; then
  args+=(--dry-run)
fi

if [[ "${BIWENGER_DEBUG_LOG:-0}" == "1" ]]; then
  args+=(--debug-log)
fi

args+=("$@")

echo "Repo: $REPO_ROOT"
echo "Python: $PY"
echo "Command: $PY ${args[*]}"

biwenger_notify "Biwenger Players" "Player scraping started."

if "$PY" "${args[@]}"; then
  echo "Completed at: $(date)"
  biwenger_notify "Biwenger Players" "Player scraping completed."
  exit 0
else
  code=$?
  echo "Failed at: $(date)"
  echo "Exit code: $code"
  biwenger_notify "Biwenger Players" "Player scraping failed with exit code $code."
  exit "$code"
fi

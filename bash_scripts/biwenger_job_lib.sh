#!/usr/bin/env bash

# Shared helpers for launchd-friendly Biwenger scheduler scripts.

biwenger_repo_root() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
  cd "$script_dir/.." && pwd
}

biwenger_prepare_env() {
  export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
  export LANG="en_US.UTF-8"
  export LC_ALL="en_US.UTF-8"
}

biwenger_python() {
  local repo_root="$1"
  local py="$repo_root/.venv/bin/python"

  if [[ ! -x "$py" ]]; then
    echo "Missing executable Python virtualenv at $py" >&2
    echo "Create it and install dependencies before running scheduler jobs." >&2
    return 90
  fi

  printf '%s\n' "$py"
}

biwenger_start_log() {
  local repo_root="$1"
  local job_name="$2"
  local retention_days="${3:-7}"
  local timestamp
  local log_root
  local log_dir

  timestamp="$(date -u '+%Y%m%dT%H%M%SZ')"
  log_root="$repo_root/run_artifacts/launchd/$job_name"
  log_dir="$log_root/$timestamp"

  mkdir -p "$log_dir"
  if [[ -d "$log_root" ]]; then
    find "$log_root" -mindepth 1 -maxdepth 1 -type d -mtime +"$retention_days" -exec rm -rf {} +
  fi

  export BIWENGER_JOB_LOG="$log_dir/script.log"
  exec >>"$BIWENGER_JOB_LOG" 2>&1

  echo "Scheduler log: $BIWENGER_JOB_LOG"
  echo "Started at: $(date)"
}

biwenger_notify() {
  local title="$1"
  local message="$2"

  if [[ "${BIWENGER_NOTIFY:-1}" == "0" ]]; then
    return 0
  fi

  if command -v osascript >/dev/null 2>&1; then
    /usr/bin/osascript -e 'display notification "'"$message"'" with title "'"$title"'"' || true
  fi
}

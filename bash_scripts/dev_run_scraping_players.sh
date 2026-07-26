#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export BIWENGER_DRY_RUN="${BIWENGER_DRY_RUN:-1}"
export BIWENGER_MAX_PLAYER_PAGES="${BIWENGER_MAX_PLAYER_PAGES:-1}"
export BIWENGER_MAX_PLAYERS="${BIWENGER_MAX_PLAYERS:-2}"

exec "$SCRIPT_DIR/run_players.sh" "$@"

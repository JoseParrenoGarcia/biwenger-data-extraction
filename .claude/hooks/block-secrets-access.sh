#!/usr/bin/env bash
# PreToolUse hook: blocks Claude from reading/writing real files under secrets/.
# Reads the hook JSON payload from stdin and delegates matching to secrets_guard.py.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PAYLOAD="$(cat)"

REASON="$(printf '%s' "$PAYLOAD" | python3 -c "
import sys, json
sys.path.insert(0, '$SCRIPT_DIR/lib')
from secrets_guard import is_blocked

payload = json.load(sys.stdin)
reason = is_blocked(payload)
if reason:
    print(reason)
")"

if [[ -n "$REASON" ]]; then
    echo "$REASON" >&2
    exit 2
fi

exit 0

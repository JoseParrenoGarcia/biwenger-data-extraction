#!/usr/bin/env bash
set -euo pipefail
/usr/bin/osascript -e 'display notification "Job ran at '"$(/bin/date)"'" with title "Biwenger Cron"'

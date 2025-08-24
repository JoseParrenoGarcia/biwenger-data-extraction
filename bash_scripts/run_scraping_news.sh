#!/bin/bash

# Move to project root directory
cd "$(dirname "$0")/.."

# Set PYTHONPATH
export PYTHONPATH=$(pwd)

# macOS notification: script starting
osascript -e 'display notification "Scraping started..." with title "Biwenger Cron"'

# Run the Python scraping runner (with flags like --test)
python3 scraping_news/runner.py "$@"
exit_code=$?

# macOS notification: script completed
if [ $exit_code -eq 0 ]; then
  osascript -e 'display notification "Scraping completed successfully." with title "Biwenger Cron"'
else
  osascript -e 'display notification "Scraping failed ❌. Check logs." with title "Biwenger Cron"'
fi

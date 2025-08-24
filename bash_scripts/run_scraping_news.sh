#!/bin/bash

# Move to project root directory
cd "$(dirname "$0")/.."

# Ensure the project root is in PYTHONPATH
export PYTHONPATH=$(pwd)

# Run the Python scraping runner, passing along any flags like --test
python3 scraping_news/runner.py "$@"

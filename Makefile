# Makefile for Biwenger Data Extraction Project

# Set the default shell
SHELL := /bin/bash

# Python executable (customize if using a virtualenv)
PYTHON ?= .venv/bin/python

# ────────────────────────────────────────────────────────────────
# SCRAPING PIPELINE TARGETS
# ────────────────────────────────────────────────────────────────

.PHONY: scrape-players
scrape-players:
	@echo "🔁 Running Biwenger player scraping pipeline..."
	bash bash_scripts/run_players.sh

.PHONY: scrape-current-team
scrape-current-team:
	@echo "👥 Running Biwenger current-team scraping pipeline..."
	bash bash_scripts/run_current_team.sh

.PHONY: scheduler-test-players-2
scheduler-test-players-2:
	@echo "🔁 Running scheduler-shaped 2-player player scrape..."
	BIWENGER_MAX_PLAYER_PAGES=1 BIWENGER_MAX_PLAYERS=2 bash bash_scripts/run_players.sh

.PHONY: test
test:
	@echo "🧪 Running unit tests..."
	$(PYTHON) -m pytest

.PHONY: lint
lint:
	@echo "🔎 Running Ruff lint..."
	$(PYTHON) -m ruff check .

.PHONY: format-check
format-check:
	@echo "🧹 Checking Ruff formatting..."
	$(PYTHON) -m ruff format --check .

.PHONY: ci
ci: lint format-check test
	@echo "✅ Local CI checks completed."

.PHONY: dry-run-team
dry-run-team:
	@echo "👥 Running headed current-team dry run..."
	$(PYTHON) -m scraping_biwenger.get_current_team --headed --dry-run

.PHONY: dry-run-player-kita
dry-run-player-kita:
	@echo "🎯 Running headed targeted player dry run: kazunari-kita..."
	$(PYTHON) -m scraping_biwenger.get_player_stats --headed --dry-run --player-slug kazunari-kita

.PHONY: dry-run-player-mbappe
dry-run-player-mbappe:
	@echo "🎯 Running headed targeted player dry run: mbappe..."
	$(PYTHON) -m scraping_biwenger.get_player_stats --headed --dry-run --player-slug mbappe

.PHONY: dry-run-players-2
dry-run-players-2:
	@echo "🔎 Running headed 2-player dry run..."
	$(PYTHON) -m scraping_biwenger.get_player_stats --headed --dry-run --max-player-pages 1 --max-players 2

.PHONY: dry-run-players-15
dry-run-players-15:
	@echo "🔎 Running headed 15-player dry run..."
	$(PYTHON) -m scraping_biwenger.get_player_stats --headed --dry-run --max-player-pages 2 --max-players 15

.PHONY: dry-run-ladder
dry-run-ladder: test dry-run-player-kita dry-run-player-mbappe dry-run-players-2
	@echo "✅ Basic player verification ladder completed."

.PHONY: dry-run-ladder-broad
dry-run-ladder-broad: dry-run-ladder dry-run-team dry-run-players-15
	@echo "✅ Broad headed verification ladder completed."

.PHONY: write-players-2
write-players-2:
	@echo "⬆️  Running headed 2-player scrape with Supabase writes..."
	$(PYTHON) -m scraping_biwenger.get_player_stats --headed --max-player-pages 1 --max-players 2 --upload-batch-size 10

.PHONY: upload-checkpoint
upload-checkpoint:
	@test -n "$(CHECKPOINT_DIR)" || (echo "Set CHECKPOINT_DIR=run_artifacts/player_runs/<run_id>"; exit 1)
	@echo "⬆️  Uploading checkpoint $(CHECKPOINT_DIR) to Supabase without scraping..."
	$(PYTHON) -m scraping_biwenger.get_player_stats --upload-checkpoint "$(CHECKPOINT_DIR)"


# ────────────────────────────────────────────────────────────────
# DEPENDENCY MANAGEMENT
# ────────────────────────────────────────────────────────────────

.PHONY: install
install:
	@echo "📦 Installing requirements..."
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

.PHONY: supabase-bootstrap
supabase-bootstrap:
	@echo "🧱 Applying Supabase migrations..."
	supabase db push

.PHONY: supabase-check
supabase-check:
	@echo "🔌 Checking Supabase connection..."
	$(PYTHON) -m supabase_client.connection

# ────────────────────────────────────────────────────────────────
# COMBINED / FUTURE TARGETS
# ────────────────────────────────────────────────────────────────

.PHONY: all
all: scrape-players

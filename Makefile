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
	@echo "👥 Running Biwenger current-team pipeline..."
	bash bash_scripts/run_current_team.sh

.PHONY: test
test:
	@echo "🧪 Running unit tests..."
	$(PYTHON) -m pytest -m "not integration"

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

.PHONY: dry-run-player-marc-roca
dry-run-player-marc-roca:
	@echo "🎯 Running headed targeted player dry run: marc-roca..."
	$(PYTHON) -m scraping_biwenger.get_player_stats --headed --dry-run --player-slug marc-roca

.PHONY: dry-run-player-gueye
dry-run-player-gueye:
	@echo "🎯 Running headed targeted player dry run: maguette-gueye..."
	$(PYTHON) -m scraping_biwenger.get_player_stats --headed --dry-run --player-slug maguette-gueye

.PHONY: dry-run-players-2
dry-run-players-2:
	@echo "🔎 Running headed 2-player dry run..."
	$(PYTHON) -m scraping_biwenger.get_player_stats --headed --dry-run --max-player-pages 1 --max-players 2

.PHONY: run-players-ui
run-players-ui:
	@echo "🖥️  Running headed 2-player dry run with terminal UI..."
	$(PYTHON) -m scraping_biwenger.get_player_stats --headed --dry-run --terminal-ui --max-player-pages 1 --max-players 2

.PHONY: run-players-ui-write-2
run-players-ui-write-2:
	@echo "🖥️  Running headed 2-player scrape with terminal UI and Supabase writes..."
	$(PYTHON) -m scraping_biwenger.get_player_stats --headed --terminal-ui --max-player-pages 1 --max-players 2 --upload-batch-size 10

.PHONY: run-players-ui-full
run-players-ui-full:
	@echo "🖥️  Running headed full player scrape with terminal UI and Supabase writes..."
	$(PYTHON) -m scraping_biwenger.get_player_stats --headed --terminal-ui --upload-batch-size 10

.PHONY: run-players-ui-popup
run-players-ui-popup:
	@echo "🪟 Opening a separate Terminal window for the player UI dry run..."
	bash bash_scripts/run_players_ui_popup.sh

.PHONY: run-players-ui-popup-write-2
run-players-ui-popup-write-2:
	@echo "🪟 Opening a separate Terminal window for the 2-player UI write run..."
	bash bash_scripts/run_players_ui_popup.sh --headed --terminal-ui --max-player-pages 1 --max-players 2 --upload-batch-size 10

.PHONY: run-players-ui-popup-full
run-players-ui-popup-full:
	@echo "🪟 Opening a separate Terminal window for the full UI write run..."
	bash bash_scripts/run_players_ui_popup.sh --headed --terminal-ui --upload-batch-size 10

.PHONY: dry-run-players-15
dry-run-players-15:
	@echo "🔎 Running headed 15-player dry run..."
	$(PYTHON) -m scraping_biwenger.get_player_stats --headed --dry-run --max-player-pages 2 --max-players 15

.PHONY: dry-run-ladder
dry-run-ladder: test dry-run-player-kita dry-run-player-mbappe dry-run-players-2
	@echo "✅ Basic player verification ladder completed."

.PHONY: dry-run-player-regressions
dry-run-player-regressions: dry-run-player-kita dry-run-player-marc-roca dry-run-player-gueye
	@echo "✅ Targeted player regression checks completed."

.PHONY: dry-run-ladder-broad
dry-run-ladder-broad: dry-run-ladder dry-run-player-regressions dry-run-team dry-run-players-15
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
# DASHBOARD TARGETS
# ────────────────────────────────────────────────────────────────

.PHONY: dashboard
dashboard:
	@echo "📊 Starting Biwenger dashboard..."
	$(PYTHON) -m streamlit run dashboard/app.py

.PHONY: test-integration
test-integration:
	@echo "🔌 Running integration tests (requires live Supabase)..."
	$(PYTHON) -m pytest -m integration tests/test_dashboard_queries.py -v


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

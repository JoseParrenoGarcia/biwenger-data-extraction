# Makefile for Biwenger Data Extraction Project

# Set the default shell
SHELL := /bin/bash

# Python executable (customize if using a virtualenv)
PYTHON := python3

# ────────────────────────────────────────────────────────────────
# SCRAPING PIPELINE TARGETS
# ────────────────────────────────────────────────────────────────

.PHONY: scrape-players
scrape-players:
	@echo "🔁 Running Biwenger player scraping pipeline..."
	bash bash_scripts/run_scraping_players.sh


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

# Future:
# make test
# make lint

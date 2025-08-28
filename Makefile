# Makefile for Biwenger Data Extraction Project

# Set the default shell
SHELL := /bin/bash

# Python executable (customize if using a virtualenv)
PYTHON := python3

# ────────────────────────────────────────────────────────────────
# SCRAPING PIPELINE TARGETS
# ────────────────────────────────────────────────────────────────

.PHONY: scrape-news
scrape-news:
	@echo "🔁 Running full scraping pipeline..."
	bash bash_scripts/run_scraping_news.sh


.PHONY: scrape-players
scrape-players:
	@echo "🔁 Running full scraping pipeline..."
	bash bash_scripts/run_scraping_players.sh


# ────────────────────────────────────────────────────────────────
# DEPENDENCY MANAGEMENT
# ────────────────────────────────────────────────────────────────

.PHONY: install
install:
	@echo "📦 Installing requirements..."
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

# ────────────────────────────────────────────────────────────────
# COMBINED / FUTURE TARGETS
# ────────────────────────────────────────────────────────────────

.PHONY: all
all: scrape-news

# Future:
# make test
# make lint

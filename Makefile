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

.PHONY: scrape-news-test
scrape-news-test:
	@echo "🧪 Running scraping pipeline in test mode..."
	bash bash_scripts/run_scraping_news.sh --test

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

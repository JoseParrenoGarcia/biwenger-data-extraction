# Repository Architecture Audit

Date: 2026-07-18

Status note: the news scraping, structured news, and LLM client subsystems
described below were removed after this audit. Keep this document as historical
context for the cleanup rationale, not as the current runtime map.

## Executive summary

This repository is a Python ETL project for collecting fantasy football data for Biwenger. It currently combines three concerns:

1. Scraping Biwenger application data with Playwright.
2. Scraping and enriching football news articles with HTTP scraping plus LLM calls.
3. Writing both raw and derived data into Supabase tables.

The likely target core is the Biwenger data extraction pipeline. The news scraping and structured news pipelines are large, coupled, and scheduled as a single daily "news" job. If the goal is to completely remove news scraping and structured news, removal must include code, tests, Makefile targets, launchd templates, log artifacts, Supabase schema references, and LLM dependencies that only exist for news.

The repo has basic unit tests, but they mostly cover the news modules that are candidates for removal. There is little or no direct test coverage for the Biwenger scraping behavior, Playwright flows, or Supabase write semantics for player data.

## Current top-level layout

```text
.
|-- scraping_biwenger/     Core Biwenger app scraping and player ETL
|-- scraping_news/         News URL/article scraping and LLM article enrichment
|-- structured_news/       LLM Markdown digest generation from scraped articles
|-- llm_client/            OpenAI, Gemini, and local Ollama adapters
|-- supabase_client/       Supabase connection and generic DB utilities
|-- bash_scripts/          macOS/launchd-friendly wrapper scripts
|-- launchd/               LaunchAgent templates and setup notes
|-- tests/                 Unit tests, mostly for scraping_news and Supabase config
|-- logs/                  Tracked runtime log files
|-- requirements.txt       Python dependency pins
|-- Makefile               Convenience targets for scraping jobs
|-- README.md              One-line project description
```

## Runtime entry points

### Makefile

- `make scrape-players` runs `bash bash_scripts/run_scraping_players.sh`.
- `make scrape-news` runs `bash bash_scripts/run_scraping_news.sh`.
- `make all` currently aliases `scrape-news`, which means the default combined target is pointed at a removal candidate.
- `make install` installs `requirements.txt`.

### Shell scripts

- `bash_scripts/run_scraping_players.sh`
  - Sets a fixed local repo path.
  - Sets `PYTHONPATH`.
  - Prefers `.venv/bin/python`.
  - Sends macOS notifications through `osascript`.
  - Runs `python -m scraping_biwenger.runner run_scraping_players`.
  - `scraping_biwenger.runner` now parses the legacy `run_scraping_players` argument explicitly.

- `bash_scripts/dev_run_scraping_players.sh`
  - Same wrapper pattern.
  - Runs `python -m scraping_biwenger.get_player_stats run_scraping_players`.
  - This is now a development shell wrapper around the standard player stats CLI.

- `bash_scripts/run_scraping_news.sh`
  - Runs `scraping_news/runner.py`.
  - Then runs `structured_news/runner.py` regardless of the first job's success.
  - Returns non-zero if either job failed.
  - This is the main shell-level coupling between raw news scraping and structured news.

- `bash_scripts/notify_test.sh`
  - Simple launchd notification probe.

### launchd templates

- `launchd/launchd_scrape_players.txt` is a script template, not a plist, despite living under `launchd`.
- `launchd/launchd_scrape_news.txt` is a LaunchAgent plist template pointing to `/Users/joseparreno/bin/run_scraping_news.sh`.
- `launchd/launchagent_test_guide.md` documents the macOS LaunchAgent setup.
- `launchd/launchd_tester_script.txt` is a LaunchAgent plist for notification testing.

The launchd layer is local-machine specific. It hardcodes user paths and is not portable.

## Functional architecture

```text
Biwenger credentials
      |
      v
Playwright browser session
      |
      +--> scraping_biwenger/get_current_team.py
      |       -> biwenger_current_team
      |
      +--> scraping_biwenger/get_player_stats.py
              -> biwenger_player_stats
              -> biwenger_player_matches
              -> biwenger_player_value

News landing pages
      |
      v
scraping_news/get_relevant_articles.py
      -> article_urls
      |
      v
scraping_news/get_article_contents.py
      -> article_contents
      |
      v
structured_news/*.py
      -> article_for_streamlit
```

## Biwenger pipeline

### `scraping_biwenger/runner.py`

The player pipeline runner orchestrates two ETL stages:

1. `ETL_get_current_team()`
2. `ETL_get_player_stats()`

It logs total and per-step durations into `logs/runner_scraping_biwenger.log`.

### Shared Biwenger helpers

Shared browser and login behavior now lives under `scraping_biwenger/shared/`:

- Loads credentials from `secrets/biwenger.toml`.
- Supports multiple credential profiles, currently including default `biwenger` and `biwenger_player_scraper`.
- Starts Chromium through Playwright.
- Accepts the Didomi cookie banner if present.
- Clicks through login and navigates to `https://biwenger.as.com/app`.
- Provides generic helpers for tab navigation and scroll behavior.

Risk: credential location and profile names are hardcoded. There is no environment-variable fallback.

### `scraping_biwenger/get_current_team.py`

Purpose: scrape the user's current Biwenger squad table.

Flow:

1. Load default Biwenger credentials.
2. Open a headless Playwright session.
3. Log in.
4. Navigate to the `team` tab.
5. Switch the squad view to table mode.
6. Scrape one row per squad player.
7. Delete all existing rows from `biwenger_current_team`.
8. Insert the fresh snapshot.

Extracted fields include:

- `name`
- `points`
- `market_value`
- `mv_change_eur`
- `status`
- `games_played`
- `average_points`
- `form_t-1` through `form_t-5`

Important behavior:

- The table is effectively treated as current state, not history.
- It clears the target table using `delete().neq("id", 0)`, which assumes an integer-like `id` column and "truncate" semantics.

### `scraping_biwenger/get_player_stats.py`

Purpose: scrape the wider player list, player detail panels, match history, and market value history.

Flow:

1. Load `biwenger_player_scraper` credentials.
2. Open a headless Playwright session.
3. Log in.
4. Navigate to the `players` tab.
5. Switch to table mode.
6. Extract all player names and slugs.
7. For each player:
   - Open the player detail view through search.
   - Scrape left-panel player details.
   - Scrape match history from the points tab.
   - Scrape value history from the value tab, including CSV download.
8. Write to Supabase:
   - `biwenger_player_stats`
   - `biwenger_player_matches`
   - `biwenger_player_value`

Write semantics:

- `biwenger_player_stats`: deletes today's rows per `(player_name, team)`, then inserts the fresh snapshot.
- `biwenger_player_matches`: deletes rows per `(player_name, team, match_date)` for dates scraped in the current run, then inserts replacements.
- `biwenger_player_value`: fetches existing value rows per slug and date range, inserts only new or changed records, and deletes changed dates before reinserting.

Notable implementation issue:

- The value change comparison uses:

```python
changed_mask = g["date"].isin(existing["date"]) & (g["market_value_eur"] != g["date"].map(db_map))
```

`db_map` maps date to market value, so the expression works mechanically, but the coupling is subtle and should be tested directly.

### Biwenger player modules

Player-specific scraping helpers now live under `scraping_biwenger/players/`:

- `discover.py`
  - Paginates or scrolls the players table and extracts player identity metadata.

- `search_and_open.py`
  - Focuses and clears search, types a player name, waits for filtered results, opens player detail, and returns to the table.

- `detail.py`
  - Parses the player detail panel. Includes several parsing helpers for integers, floats, percentages, money, status, team, position, and season labels.

- `matches.py`
  - Opens the points tab and scrapes match rows, including season, round, date, points, best XI, and events.

- `value_history.py`
  - Opens the value tab, downloads CSV data, normalizes value history into a dataframe, and attaches player context.

- `detail_loop.py`
  - Coordinates detail, match, and value scraping for every player.

## News scraping pipeline - removal candidate

The `scraping_news/` package is responsible for discovering article URLs, extracting article contents, and enriching those articles with LLM metadata.

### `scraping_news/runner.py`

Current flow:

1. `ETL_get_relevant_articles(test=test)`
2. `ETL_get_article_contents(test=test)` is called by the runner, but the actual function signature does not accept `test`.

This is a bug: `ETL_get_article_contents()` is defined without parameters, so `run_full_scraping_pipeline(test=True/False)` will raise `TypeError` when it reaches step 3 if the call path is exercised as written.

The specialised match-preview step exists but is commented out.

### `scraping_news/get_relevant_articles.py`

Purpose: discover relevant news URLs and insert them into `article_urls`.

Flow:

1. Load configured landing pages from `config_landing_pages.py`.
2. Instantiate `Website` for each landing page.
3. Extract links.
4. Deduplicate links within each source.
5. Query existing `(team, url)` pairs from `article_urls`.
6. Filter out existing URLs.
7. Ask an LLM to filter relevance by team.
8. Parse the LLM response with `ast.literal_eval`.
9. Flatten to `{team, source, url}` rows.
10. Insert deduplicated rows into `article_urls`.

Risks:

- LLM output is parsed as Python literals rather than strict JSON.
- Relevance filtering fallback keeps unfiltered links when LLM parsing fails.
- The source configuration has at least one likely string concatenation bug in the Valencia list: one URL string is missing a comma before the following `as.com` URL.
- It runs concurrent LLM filtering with a hardcoded worker count.

### `scraping_news/get_article_contents.py`

Purpose: scrape full article bodies for URLs in `article_urls`, then enrich them with LLM metadata and insert into `article_contents`.

Flow:

1. Query `article_urls`.
2. Query existing `article_contents.article_id`.
3. Scrape only URLs whose `article_id` is not already in `article_contents`.
4. Extract article text, title, and publication date through `Website`.
5. Call LLM to generate:
   - `summary_llm`
   - `tags_llm`
   - `recognised_teams_llm`
   - `recognised_people_llm`
6. Insert enriched rows into `article_contents`.

Risks:

- It advertises "parallel" work in logging but uses `ThreadPoolExecutor(max_workers=1)`.
- The function signature mismatch with `scraping_news/runner.py` is a runtime bug.
- It uses `ast.literal_eval` to parse LLM output.
- It contains unresolved merge-conflict comments in a commented block.
- Article scraping is generic and has a high failure risk for dynamic, paywalled, blocked, or non-standard pages.

### `scraping_news/get_specialised_articles.py`

Purpose: scrape deterministic match preview links, primarily from `jornadaperfecta.com/onces-posibles`, then insert them into `article_urls`.

Current status:

- Imported by `scraping_news/runner.py`.
- The actual ETL step is commented out in the runner.
- Tests still cover `scrape_match_preview_links`.

### `scraping_news/scraper_utils.py`

Provides `Website`, a requests + BeautifulSoup scraper.

Capabilities:

- Fetch HTML with a browser-like user agent.
- Extract normalized links.
- Extract title.
- Extract article text using `<article>`, common CMS selectors, or longest paragraph cluster.
- Extract published date from JSON-LD, meta tags, or `<time datetime>`.

Dependencies:

- `requests`
- `beautifulsoup4`

Both are required by code but are not listed explicitly in `requirements.txt`.

### `scraping_news/config_landing_pages.py`

Contains hardcoded LaLiga team news source URLs and test sources. This is a pure data/config module for the news pipeline and can be removed with it.

### `scraping_news/llm_prompts.py`

Contains Spanish prompts for:

- URL relevance filtering.
- Article summary, tags, teams, and people extraction.

This is specific to the news pipeline.

## Structured news pipeline - removal candidate

The `structured_news/` package generates Markdown reports from `article_contents` and writes them to `article_for_streamlit`.

It depends on the raw news pipeline. If `scraping_news` is removed, `structured_news` loses its input tables and should also be removed unless a replacement article source is introduced.

### `structured_news/runner.py`

Flow:

1. Connect to Supabase.
2. Check `article_for_streamlit`.
3. Delete all existing rows from `article_for_streamlit`.
4. Run:
   - `ETL_get_injury_news()`
   - `ETL_get_transfer_news()`
   - `ETL_get_next_match_news()`
   - `ETL_get_previous_match_news()`

Risk:

- It clears the output table before generating new content. If a later stage fails, the previous Streamlit content has already been deleted.

### `structured_news/get_injury_news.py`

Builds an injury/disavailability Markdown digest for each team.

Inputs:

- Teams from `article_urls`.
- Recent records from `article_contents`.
- Tags from `MODULE_PROFILES["lesiones"]`.

Output:

- Inserts `{team, tag, markdown_document}` into `article_for_streamlit`.

### `structured_news/get_transfer_news.py`

Builds a transfer-market Markdown digest for each team.

Inputs:

- Teams from `article_urls`.
- Recent records from `article_contents`.
- Tags from `MODULE_PROFILES["transfers"]`.

Output:

- Inserts into `article_for_streamlit`.

### `structured_news/get_next_match_news.py`

Builds probable-lineup/next-match Markdown digests.

Inputs:

- Teams from `article_urls`.
- Recent records from `article_contents`.
- Tags from `MODULE_PROFILES["previa_siguiente_partido"]`.

Output:

- Inserts into `article_for_streamlit`.

### `structured_news/get_previous_match_summaries.py`

Builds recent-match chronicle Markdown digests focused on individual performances useful for Biwenger managers.

Inputs:

- Teams from `article_urls`.
- Recent records from `article_contents`.
- Tags from `MODULE_PROFILES["cronica_partido"]`.

Output:

- Inserts into `article_for_streamlit`.

Observations:

- It follows the same fetch, filter, prompt, LLM, insert pattern as the other structured news modules.
- Some log messages still refer to "injury" or "transfer" tags even though the module handles previous-match chronicles.
- The system prompt says "alineacion probable del proximo partido" even though the user prompt and ETL name are about previous match summaries. This is likely prompt drift from copy/paste.

### `structured_news/utils.py`

Shared helpers:

- `MODULE_PROFILES`
- Fetch unique teams from a Supabase table.
- Fetch recent articles by `published_date`.
- Filter articles by team and tag.
- Coerce array-like values from strings/lists/numpy arrays.
- Build compact article payloads for LLM prompts.

This module is specific to structured news and can be removed if structured news is removed.

## LLM client layer

The `llm_client/` package provides a provider fallback abstraction for LLM tasks.

### `llm_client/llm_orchestrator.py`

Main function:

- `call_llm(system_prompt, user_prompt, model_priority=["gemini", "openai"], ...)`

Supported vendors:

- `gemini`
- `openai`
- `local` through an Ollama-compatible OpenAI client

Secrets expected:

- `secrets/googleAI.toml`
- `secrets/openAI.toml`
- `secrets/local.toml`

Observations:

- This package is only used by `scraping_news` and `structured_news`.
- If both news packages are removed, `llm_client` likely becomes unused and removable.
- `llm_client/openai_utils.py` imports `tiktoken`, and `llm_client/llm_orchestrator.py` imports `OpenAI`; neither `tiktoken` nor `openai` is explicitly pinned in `requirements.txt`.

## Supabase client layer

### `supabase_client/connection.py`

Provides:

- `get_supabase_client(secrets_path_override=None)`

Expected default secret:

- `secrets/supabase.toml`

Required fields:

- `[supabase].url`
- `[supabase].anon_key`

The tests cover missing file, missing keys, and valid local TOML structure.

### `supabase_client/utils.py`

Generic DB utilities:

- `check_if_table_exists`
- `insert_rows_into_table`
- `insert_rows_into_table_batched`
- `upsert_rows_into_table`
- hash helper
- player value delta helpers
- row deletion helpers for stats, matches, and values

The later half of the module is Biwenger-player-specific despite living in a generic Supabase utility module. This should be split later into:

- generic Supabase persistence helpers
- Biwenger player repository/write helpers

### `supabase_client/supabase_schema_reference.sql`

Currently documents only:

- `article_urls`
- `article_contents`

It does not document the active Biwenger tables used by the current core pipeline:

- `biwenger_current_team`
- `biwenger_player_stats`
- `biwenger_player_matches`
- `biwenger_player_value`

If news is removed, this schema reference becomes mostly obsolete and should be replaced with a Biwenger-focused schema reference.

## Data stores and tables

Observed Supabase tables by pipeline:

| Table | Used by | Purpose | Future status |
|---|---|---|---|
| `biwenger_current_team` | `get_current_team.py` | Current squad snapshot | Keep |
| `biwenger_player_stats` | `get_player_stats.py` | Daily player detail snapshots | Keep |
| `biwenger_player_matches` | `get_player_stats.py` | Player match history rows | Keep |
| `biwenger_player_value` | `get_player_stats.py` | Player market value history | Keep |
| `article_urls` | `scraping_news`, `structured_news` | News URL staging | Remove candidate |
| `article_contents` | `scraping_news`, `structured_news` | Article text and LLM metadata | Remove candidate |
| `article_for_streamlit` | `structured_news` | Generated Markdown reports | Remove candidate |

## Tests

Command run during audit:

```bash
.venv/bin/pytest
```

Result:

```text
44 passed in 18.23s
```

Coverage shape:

- Strongest coverage is for `scraping_news`.
- Supabase connection config has a few useful tests.
- There is no meaningful test coverage for:
  - Biwenger login flow.
  - Playwright page navigation.
  - Player table parsing.
  - Player detail parsing.
  - Supabase write semantics for Biwenger player data.
  - Runner scripts.
  - Makefile targets.

The global `pytest` command was not available on PATH in the shell; `.venv/bin/pytest` worked.

## Dependencies

Pinned in `requirements.txt`:

```text
crawl4ai==0.6.2
pandas==2.2.3
playwright==1.52.0
pytest==8.4.0
toml==0.10.2
google-generativeai==0.8.5
supabase==2.18.1
```

Observed imports not explicitly pinned:

- `requests`
- `beautifulsoup4` / `bs4`
- `openai`
- `tiktoken`
- `numpy`
- `postgrest`

Some may arrive transitively through installed packages, but relying on transitive dependencies is fragile.

Potential unused or removable dependencies after news removal:

- `crawl4ai`: not observed in source imports.
- `google-generativeai`: likely removable if `llm_client` is removed.
- `openai`, `tiktoken`, `requests`, `beautifulsoup4`: likely removable if news/LLM features are removed.

Likely keep:

- `pandas`
- `playwright`
- `pytest`
- `toml` or standard-library `tomllib` depending on Python version policy
- `supabase`

## Repository hygiene observations

### Tracked logs

Runtime logs are tracked by Git. Examples:

- `logs/*.log`
- `scraping_biwenger/logs/*.log`
- `scraping_news/logs/*.log`
- `structured_news/logs/*.log`
- `llm_client/logs/*.log`

This causes noisy working trees. At audit time, the following tracked logs were already modified:

- `logs/ETL_get_current_team.log`
- `logs/ETL_get_player_stats.log`
- `logs/ETL_get_relevant_articles.log`
- `logs/runner_scraping_biwenger.log`
- `logs/runner_scraping_news.log`

Recommendation: add log ignore rules and remove tracked log files from Git in a cleanup branch.

### Generated files and local state

The `.gitignore` ignores:

- `__pycache__/`
- `.venv/`
- `venv/`
- `.env`
- `.idea/`
- `secrets/`

The filesystem still contains local `.venv`, `.pytest_cache`, `.idea`, `__pycache__`, and `secrets` directories. Most are ignored, but logs are not ignored.

### Secrets

The code expects secrets under `secrets/`. The directory is ignored and was not listed as tracked by `git ls-files`, which is good.

Expected files:

- `secrets/biwenger.toml`
- `secrets/supabase.toml`
- `secrets/googleAI.toml`
- `secrets/openAI.toml`
- `secrets/local.toml`

Recommendation: add `secrets/*.example.toml` templates and document environment setup without exposing actual secrets.

### README

The README currently has only a title and one descriptive sentence. It does not explain:

- setup
- secrets
- commands
- schedule
- tables
- pipeline architecture
- testing
- cleanup roadmap

### CI

`.github/workflows/test.yml`:

- Runs on `main` pushes and PRs.
- Uses Python 3.13.
- Installs `requirements.txt` and pytest.
- Runs `pytest`.

Risks:

- The requirements file may be incomplete relative to imports.
- The test suite currently exercises modules that are planned for removal.
- There is no linting, formatting, type checking, or integration-test strategy.

## News removal blast radius

If the intent is to completely remove news scraping and structured news, consider the following references:

### Delete candidate directories/files

- `scraping_news/`
- `structured_news/`
- `tests/scraping_news/`
- `llm_client/` if no future non-news LLM use is planned
- `bash_scripts/run_scraping_news.sh`
- `launchd/launchd_scrape_news.txt`
- news-related logs under `logs/`, `scraping_news/logs/`, `structured_news/logs/`, and `llm_client/logs/`

### Update candidate files

- `Makefile`
  - Remove `scrape-news`.
  - Change `all` from `scrape-news` to likely `scrape-players`.

- `README.md`
  - Rewrite around the kept Biwenger player data pipeline.

- `requirements.txt`
  - Remove LLM/news-only dependencies after confirming imports.
  - Add explicit direct dependencies for any kept imports.

- `supabase_client/supabase_schema_reference.sql`
  - Remove article schema or move it to archived docs.
  - Add Biwenger table schemas.

- `.gitignore`
  - Add log ignore rules.

- `.github/workflows/test.yml`
  - Ensure remaining tests do not import deleted packages.

### Database cleanup candidates

If no downstream app still uses them:

- `article_urls`
- `article_contents`
- `article_for_streamlit`

Before dropping these, confirm whether an external Streamlit app or dashboard still reads `article_for_streamlit`.

### Dependencies likely removable with news

- `google-generativeai`
- `openai`
- `tiktoken`
- `requests`
- `beautifulsoup4`
- `crawl4ai` if still unused

## Refactoring needs for the kept core

These are not changes made in this audit. They are future issue candidates.

### 1. Define target scope

Decide whether the repo is:

- a Biwenger-only data extractor, or
- a broader football intelligence ETL.

Given the stated intent to remove news scraping and structured news, the simpler target is a Biwenger-only extractor.

### 2. Split orchestration, scraping, parsing, and persistence

Current ETL modules mix:

- browser session setup
- page navigation
- scraping/parsing
- dataframe shaping
- Supabase writes
- logging

A cleaner target shape:

```text
biwenger/
|-- browser.py
|-- auth.py
|-- pages/
|-- parsers/
|-- pipelines/
|-- repositories/
```

### 3. Move DB write logic out of generic utilities

`supabase_client/utils.py` contains generic helpers and Biwenger-specific deletion/delta functions. Extract the latter into a Biwenger persistence module.

### 4. Stabilize table schemas

The repo needs checked-in schema documentation for the kept tables:

- `biwenger_current_team`
- `biwenger_player_stats`
- `biwenger_player_matches`
- `biwenger_player_value`

Include primary keys, unique constraints, replace/upsert strategy, and expected column types.

### 5. Add parser-level tests for Biwenger

Full Playwright integration tests may be hard, but parser tests can cover:

- money parsing
- status normalization
- current team table extraction with fixture HTML
- player detail parsing with fixture HTML
- match row parsing
- value CSV normalization

### 6. Improve configuration

Hardcoded paths and credential file locations should move to a small config layer:

- repo-relative defaults
- optional environment-variable overrides
- documented example TOML files

### 7. Fix logging strategy

Current logger setup writes with `mode="w"`, which overwrites log files per run. Decide whether the desired behavior is:

- overwrite per run
- append
- timestamped per run
- external scheduler-managed logs

Then ignore generated logs in Git.

### 8. Simplify local automation

The scripts are macOS/launchd-oriented and hardcode a user path. Consider:

- a repo-local CLI entry point
- portable shell scripts that derive the repo path from the script location
- launchd templates that call those scripts
- clear separation between production wrappers and local notification tests

### 9. Address duplicate development modules

The duplicate development player-stats wrapper has been consolidated into the standard `get_player_stats.py` CLI. Development verification code now lives under `scraping_biwenger/dev/`.

### 10. Tighten dependency management

The requirements file should represent direct imports, not just what happens to work in a local venv. After removing news, regenerate it around the remaining core.

## Suggested cleanup issue backlog

1. Remove `scraping_news`, `structured_news`, and their tests after confirming no downstream dashboard depends on `article_for_streamlit`.
2. Remove news entry points from `Makefile`, `bash_scripts`, and `launchd`.
3. Remove or archive article-related Supabase schema references.
4. Add `.gitignore` rules for logs and remove tracked log files.
5. Replace README with setup, secrets, commands, tables, and scheduler documentation.
6. Create example secret templates.
7. Add Biwenger table schema documentation.
8. Split Biwenger persistence helpers out of `supabase_client/utils.py`.
9. Keep development verification commands consolidated under `scraping_biwenger/dev/`.
10. Add parser-level tests for Biwenger scraping helpers.
11. Make shell scripts path-portable.
12. Audit and minimize `requirements.txt`.
13. Add CI coverage for the kept modules after news tests are removed.

## Open questions

1. Is any external Streamlit app still reading `article_for_streamlit`?
2. Are `article_urls` and `article_contents` valuable historical data to archive before removing schema/code?
3. Should the repo remain macOS-only because launchd is the production scheduler, or should it support Linux/server execution too?
4. Are both Biwenger credential profiles still needed?
5. What are the expected uniqueness constraints for the four Biwenger Supabase tables?
6. Should current-team snapshots be historical, or should `biwenger_current_team` remain a replace-every-run table?

# Repository Architecture Snapshot

Date: 2026-07-19

This document is the current architecture reference for agents working in this
repository. The older architecture audit was useful during cleanup, but most of
its major recommendations have now been implemented.

## Executive Summary

This is now a Biwenger-only Python ETL project. It scrapes fantasy football data
from the Biwenger app with Playwright, normalizes the outputs with pandas, and
writes validated data to Supabase.

The repository no longer contains the old football news scraping, structured
news generation, or LLM client code. The active codebase is organized around:

1. Current-team extraction.
2. Player stats, match history, and market value extraction.
3. Shared Biwenger browser/auth/navigation helpers.
4. Supabase persistence utilities and migrations.

## Current Layout

```text
.
|-- scraping_biwenger/
|   |-- get_current_team.py       Public current-team CLI wrapper
|   |-- get_player_stats.py       Public player CLI wrapper
|   |-- runner.py                 Full Biwenger pipeline orchestration
|   |-- current_team/             Current squad scrape/transform/persist/pipeline
|   |-- players/                  Player discovery/detail/matches/value pipeline
|   |-- shared/                   Browser, auth, config, navigation, timing helpers
|   `-- dev/                      Development verification helpers
|-- supabase/
|   `-- migrations/               Supabase CLI migrations for Biwenger tables
|-- supabase_client/              Supabase connection and write helpers
|-- bash_scripts/                 macOS/launchd-friendly wrapper scripts
|-- launchd/                      Local LaunchAgent templates and setup notes
|-- docs/                         Architecture and copied Biwenger DOM notes
|-- tests/                        Unit tests for transforms, persistence, secrets
|-- secrets/                      Ignored local secrets plus safe example templates
|-- logs/                         Ignored runtime logs
|-- requirements.txt              Python dependencies
|-- Makefile                      Local convenience targets
`-- README.md                     Setup, Supabase, and runtime notes
```

The root of `scraping_biwenger/` is intentionally small. It should only contain
package-level entrypoints and top-level orchestration:

```text
scraping_biwenger/__init__.py
scraping_biwenger/get_current_team.py
scraping_biwenger/get_player_stats.py
scraping_biwenger/runner.py
```

## Runtime Entry Points

### Current Team

```bash
.venv/bin/python -m scraping_biwenger.get_current_team --headed --dry-run
```

Purpose: scrape the current squad table and optionally replace
`biwenger_current_team` in Supabase.

Important behavior:

- Uses the `biwenger` credential profile.
- Current-team rows are treated as current state, not history.
- Dry-run prints the dataframe and skips Supabase writes.
- Headed Chromium is the preferred verification mode.

### Player Stats

```bash
.venv/bin/python -m scraping_biwenger.get_player_stats --headed --dry-run --max-player-pages 1 --max-players 2
```

Purpose: scrape the player list, player detail stats, match history, and market
value history, then optionally write to:

- `biwenger_player_stats`
- `biwenger_player_matches`
- `biwenger_player_value`

Important behavior:

- Uses the `biwenger_player_scraper` credential profile.
- Dry-run prints stats, matches, and value-history dataframes and skips
  Supabase writes.
- `--player-slug <slug>` opens one player directly by Biwenger URL slug and
  skips player-list discovery.
- `--max-player-pages` limits player-table discovery.
- `--max-players` limits detail scraping.
- Headed Chromium is the preferred verification mode because headless has been
  less reliable around the Biwenger player/table UI.

### Full Runner

```bash
.venv/bin/python -m scraping_biwenger.runner
```

Purpose: run the full Biwenger scraping pipeline:

1. Current-team pipeline.
2. Player pipeline.

The runner accepts the legacy positional argument used by existing scripts:

```bash
.venv/bin/python -m scraping_biwenger.runner run_scraping_players
```

## Package Architecture

### Shared Helpers

`scraping_biwenger/shared/` owns cross-cutting Biwenger browser behavior:

- `config.py`
  - `DEFAULT_ROOT_URL`
  - `DEFAULT_APP_URL`
  - `load_biwenger_credentials()`
- `auth.py`
  - cookie banner handling
  - Play Now click
  - login form interaction
- `browser_session.py`
  - Playwright startup and initial cookie acceptance
- `navigation.py`
  - app tab navigation and scroll helpers
- `timing.py`
  - timing logs and randomized human-scale delay helper

Keep selectors and timing behavior changes separate from structural refactors
when possible.

### Current Team

`scraping_biwenger/current_team/` follows the scrape/transform/persist/pipeline
shape:

- `scrape.py`
  - extracts the visible current-team table rows.
- `transform.py`
  - normalizes names, points, money, statuses, form columns, fixture metadata,
    and player/team links.
- `persist.py`
  - validates and replaces the Supabase current-team snapshot.
- `pipeline.py`
  - logs in, navigates to the team tab, selects table layout, runs scrape and
    transform, and optionally persists.

### Players

`scraping_biwenger/players/` keeps player-owned behavior separate from
current-team behavior because it uses different credentials and writes to
different Supabase tables:

- `discover.py`
  - discovers players and slugs from the player table.
- `search_and_open.py`
  - searches the table, opens player detail, falls back to direct href when
    needed, and returns to the table between players.
- `detail.py`
  - parses the player detail panel and season/scoring metadata.
- `matches.py`
  - opens the Points tab, selects SofaScore, handles players with no round
    history, and parses match rows.
- `value_history.py`
  - opens the Value tab, downloads CSV data, and normalizes market value
    history.
- `scrape.py`
  - coordinates player discovery, targeted slug mode, and detail scraping.
- `transform.py`
  - normalizes player stats, matches, and value history dataframes.
- `persist.py`
  - writes player outputs to Supabase with slug-aware duplicate handling.
- `pipeline.py`
  - logs in with `biwenger_player_scraper`, runs scrape/transform, and
    optionally persists.

## Supabase

Schema changes are tracked in `supabase/migrations/` and should be applied with
the Supabase CLI:

```bash
supabase db push
```

The CLI is a system dependency, not a Python package, so it should not be added
to `requirements.txt`.

Normal runtime code uses `secrets/supabase.toml` with:

- `[supabase].url`
- `[supabase].anon_key`

Runtime scraping should not perform DDL. New projects should be bootstrapped via
migrations first.

Active Biwenger tables:

| Table | Purpose | Write Strategy |
|---|---|---|
| `biwenger_current_team` | Current squad snapshot | Replace all rows each run |
| `biwenger_player_stats` | Daily player detail snapshot | Slug-aware delete/insert for the run date |
| `biwenger_player_matches` | Player match history | Slug-aware delete/insert for season-aware match identities |
| `biwenger_player_value` | Market value history | Insert only new or changed value rows |

The detailed table contract and persistence semantics are maintained in
`docs/supabase_table_contracts.md`.

Historical issue #93 tracks slug backfill and future simplification of legacy
fallback identity logic.

Supabase migrations under `supabase/migrations/` are the single executable
schema source of truth. The table contract document explains semantics; it does
not replace migrations.

## Logging And Verification

Runtime logs are written under `logs/` and are intentionally ignored by Git.
Recent scraper work added timing logs around:

- browser startup
- cookie handling
- login
- tab navigation
- table discovery
- scoring-system selection
- player detail scraping
- match scraping
- value CSV download/parsing
- persistence

Do not commit generated logs.

## Required Testing Ladder

Use this ladder for player pipeline changes, especially selector, timing,
navigation, transform, or persistence refactors.

### Fast Unit Tests

```bash
.venv/bin/python -m pytest
```

### Current-Team Smoke Test

Use headed dry-run unless intentionally testing headless:

```bash
.venv/bin/python -m scraping_biwenger.get_current_team --headed --dry-run
```

Success means the current-team table is scraped, transformed, printed, and no
Supabase rows are written.

### Targeted Problem Player Tests

Use targeted slug mode for players known to exercise edge cases:

```bash
.venv/bin/python -m scraping_biwenger.get_player_stats --headed --dry-run --player-slug kazunari-kita
.venv/bin/python -m scraping_biwenger.get_player_stats --headed --dry-run --player-slug moussa-diarra-2
```

Why these matter:

- `kazunari-kita` previously failed when Points content did not render as the
  expected table.
- `moussa-diarra-2` is a no-round-history player and should scrape as stats
  plus value history with zero match rows.

Other historically useful names from full-run warnings:

- `Pablo Arriaza`
- `Guilherme Fernandes`
- `Edgar Alcañiz`
- `Yaakobishvili`
- `Abaida`
- `Ángel Recio`
- `Camara`
- `Sainz-Maza`
- `Sergio Martínez`
- `Aarón Ochoa`
- `Carlos López`
- `Eric Puerto`
- `Tristán`

Use exact slugs when known; otherwise first verify discovery/search behavior in
a dry-run before adding new targeted assumptions.

### Two-Player Dry-Run

```bash
.venv/bin/python -m scraping_biwenger.get_player_stats --headed --dry-run --max-player-pages 1 --max-players 2
```

Success means list discovery, search/open, one return-to-table transition, final
player skip-back behavior, transforms, and dry-run printing still work.

### Fifteen-Player Dry-Run

```bash
.venv/bin/python -m scraping_biwenger.get_player_stats --headed --dry-run --max-player-pages 2 --max-players 15
```

Success means the scraper can move beyond the first obvious table rows, handle
more navigation cycles, and recover from lower-data players without data-loss
errors.

### Supabase Write Tests

Only run write tests after dry-run output looks correct and the user explicitly
approves writing to Supabase.

Small player write:

```bash
.venv/bin/python -m scraping_biwenger.get_player_stats --headed --max-player-pages 1 --max-players 2
```

Current-team write:

```bash
.venv/bin/python -m scraping_biwenger.get_current_team --headed
```

## DOM Notes

Player detail DOM notes are in:

- `docs/player_stats_dom_notes.md`
- `docs/player_stats_html.txt`

Start with `player_stats_dom_notes.md`. The raw HTML file may contain very long
lines, so avoid pasting it into the main context. Prefer shell searches,
structured parsers, or subagents for focused inspection.

## Remaining Cleanup Backlog

The main architecture cleanup is now largely complete. Remaining valuable work:

1. Add parser-level tests for current-team HTML, player detail HTML, match row
   parsing, and value CSV normalization. Tracked by issues #68 and #71.
2. Improve README with the full testing ladder, scheduler notes, and table
   semantics. Covered across issues #70, #71, #73, and #100.
3. Make shell scripts path-portable instead of hardcoding local paths. Tracked
   by issue #73.
4. Revisit player slug backfill so legacy duplicate-protection fallback logic can
   be simplified. Tracked by issue #93.
5. Audit `requirements.txt` around direct imports and remove any remaining stale
   dependencies. Tracked by issue #68.

## Open Questions

1. Should player stats and match writes eventually become true database upserts
   with explicit unique constraints instead of application-level delete/insert?
   Tracked by issue #90.
2. Should full production runs stay headed because Biwenger is more reliable
   that way, or should headless be investigated again after selector stability
   improves? Tracked by issue #100.
3. Should the launchd/macOS scripts remain the production scheduler, or should
   the repo also support a portable Linux/server schedule? Tracked by issue #73.

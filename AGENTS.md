# Agent Context

## Repository Mission

This is an inherited repository for extracting Biwenger fantasy football data.

The target direction is a Biwenger-only data extractor focused on:

- scraping Biwenger data safely;
- extracting current-team information;
- extracting player stats, match history, and market value history;
- validating outputs before writing to Supabase;
- making the codebase easier to maintain, test, and schedule.

The current architecture snapshot is available at @docs/repo_architecture_audit.md.
Use it as the first map of the repo before planning broader refactors.

## Current Direction

The repo is in a cleanup and hardening phase. Much of the original architecture cleanup has been implemented, so prefer the current `scraping_biwenger/` package structure over older helper-file patterns.

Important current decisions:

- The repo is Biwenger-only. Article/news scraping, structured news generation, and the LLM client have been removed.
- Keep Biwenger and Supabase as the core integration points.
- Keep `biwenger_current_team` as a replace-every-run current-state table, not a historical table.
- Use the `biwenger_player_scraper` profile for high-volume scraping.
- Use the personal `biwenger` profile only where needed for current-team extraction.
- Keep root `scraping_biwenger/` limited to public entrypoints and top-level runner code. Owned implementation should live under `current_team/`, `players/`, `shared/`, or `dev/`.

## Collaboration Rules

- Interact frequently with the user during design and refactoring.
- Ask clarifying questions when the product or data decision is unclear.
- Do not silently preserve inherited behavior just because it already exists.
- Prefer small, reviewable changes with clear rationale.
- Before deleting code, identify entry points, imports, tests, scripts, schemas, and docs that reference it.
- Avoid touching secrets or printing secret values.
- Treat `secrets/` as off-limits unless the user explicitly asks for safe example templates.
- Do not commit or rely on generated logs.
- Do not commit to Git unless told so. And always create new branches, never to main.

## Engineering Preferences

- First understand the current pipeline and data flow.
- Separate orchestration, scraping, parsing, validation, and persistence over time.
- Prefer parser-level tests that do not require Biwenger, Playwright, or Supabase.
- Make test runs easy, for example limited runs with a small number of players.
- For scraper refactors, preserve behavior with a local dry-run path before changing persistence.
- Prefer verification modes that can scrape the full current team and a limited number of players while printing outputs without writing to Supabase.
- For player scraper changes, use the required dry-run ladder:
  - targeted problem player: `.venv/bin/python -m scraping_biwenger.get_player_stats --headed --dry-run --player-slug kazunari-kita`
  - targeted no-round player: `.venv/bin/python -m scraping_biwenger.get_player_stats --headed --dry-run --player-slug moussa-diarra-2`
  - normal limited run: `.venv/bin/python -m scraping_biwenger.get_player_stats --headed --dry-run --max-player-pages 1 --max-players 2`
  - broader limited run before merging risky selector/navigation changes: `.venv/bin/python -m scraping_biwenger.get_player_stats --headed --dry-run --max-player-pages 2 --max-players 15`
- For current-team scraper changes, run `.venv/bin/python -m scraping_biwenger.get_current_team --headed --dry-run`.
- Do not write to Supabase until dry-run output looks correct and the user explicitly approves a write test.
- Supabase schema bootstrap uses the Supabase CLI as a system dependency, not a Python package. Do not add the Supabase CLI to `requirements.txt`.
- Player detail DOM notes are available at @docs/player_stats_dom_notes.md. Start there when investigating player scraping selectors, timing, or parser behavior. The raw copied DOM snapshot is at @docs/player_stats_html.txt.
- If inspecting large copied Biwenger HTML dumps, prefer using subagents or narrow shell searches so the main context is not flooded with raw DOM.
- Validate dataframe columns and payload schemas before uploads.
- Keep local automation simple and documented.

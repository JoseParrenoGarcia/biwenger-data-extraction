# Agent Context

## Repository Mission

This is an inherited repository for extracting Biwenger fantasy football data.

The target direction is a Biwenger-only data extractor focused on:

- scraping Biwenger data safely;
- extracting current-team information;
- extracting player stats, match history, and market value history;
- validating outputs before writing to Supabase;
- making the codebase easier to maintain, test, and schedule.

The first architecture audit is available at @docs/repo_architecture_audit.md.

## Current Direction

The repo is in a cleanup and refactoring phase. Do not assume the existing code represents the desired final architecture.

Important current decisions:

- Remove article/news scraping.
- Remove structured news generation.
- Remove the LLM client once news/structured-news code is gone.
- Keep Biwenger and Supabase as the core integration points.
- Keep `biwenger_current_team` as a replace-every-run current-state table, not a historical table.
- Use the `biwenger_player_scraper` profile for high-volume scraping.
- Use the personal `biwenger` profile only where needed for current-team extraction.

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
- Validate dataframe columns and payload schemas before uploads.
- Keep local automation simple and documented.

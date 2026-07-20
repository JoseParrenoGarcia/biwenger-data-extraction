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
- Supabase table semantics are documented at @docs/supabase_table_contracts.md. Check that contract before changing persistence, migrations, checkpoint replay, or dashboard assumptions.
- Supabase migrations under @supabase/migrations/ are the only executable schema source of truth. Add new timestamped migrations for schema changes; do not edit already-pushed migrations or recreate duplicate schema snapshot SQL files.
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
- `secrets/` is off-limits to all AI agents (Claude, Codex, and any other agent working in this repo). Agents may inspect only `secrets/*.example.toml`. If non-secret structure or details are needed, ask the user rather than opening real files under `secrets/`.
- In this repo, Claude Code enforces this with a project-local `PreToolUse` hook (see "Active Hooks" in `CLAUDE.md`) that blocks tool calls touching real `secrets/` files. Codex does not currently have an equivalent project hook here; its protection is this `AGENTS.md` rule plus normal sandbox/session discipline — do not rely on tooling to catch a real-secret read for Codex.
- Never paste real secret values into issues, logs, docs, commit messages, or PR descriptions.
- Do not commit or rely on generated logs.
- Do not commit to Git unless told so. And always create new branches, never to main.

## Engineering Preferences

- First understand the current pipeline and data flow.
- Separate orchestration, scraping, parsing, validation, and persistence over time.
- Prefer parser-level tests that do not require Biwenger, Playwright, or Supabase.
- Make test runs easy, for example limited runs with a small number of players.
- For scraper refactors, preserve behavior with a local dry-run path before changing persistence.
- Prefer headed dry-runs that print outputs and do not write to Supabase.
- For player scraper changes, use `make dry-run-ladder` by default. It covers unit tests, `kazunari-kita`, `mbappe`, and a normal 2-player dry-run.
- For riskier player selector, navigation, timing, or parser changes, also run `make dry-run-players-15`.
- For current-team scraper changes, run `make dry-run-team`.
- Raw commands are documented in `README.md` and `docs/repo_architecture_audit.md` if Make is not convenient.
- Before committing normal code, parser, persistence, or documentation changes, run `make ci` by default. It covers Ruff linting, Ruff format checks, and pytest. Fix issues locally before committing where practical.
- Do not write to Supabase until dry-run output looks correct and the user explicitly approves a write test. Optional write checks are `make write-players-2` and `make upload-checkpoint CHECKPOINT_DIR=run_artifacts/player_runs/<run_id>`.
- Supabase schema bootstrap uses the Supabase CLI as a system dependency, not a Python package. Do not add the Supabase CLI to `requirements.txt`.
- Keep generic Supabase primitives in `supabase_client/`; Biwenger-specific table identity, delete, and delta logic belongs under `scraping_biwenger/current_team/` or `scraping_biwenger/players/`.
- Player detail DOM notes are available at @docs/player_stats_dom_notes.md. Start there when investigating player scraping selectors, timing, or parser behavior. The raw copied DOM snapshot is at @docs/player_stats_html.txt.
- If inspecting large copied Biwenger HTML dumps, prefer using subagents or narrow shell searches so the main context is not flooded with raw DOM.
- Validate dataframe columns and payload schemas before uploads.
- Keep local automation simple and documented.

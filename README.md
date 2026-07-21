# biwenger-data-extraction

Biwenger-only data extraction repository focused on scraping fantasy football data from the Biwenger app and writing validated player/team outputs to Supabase.

The repository no longer performs football news scraping, article extraction,
structured news generation, or LLM-based article enrichment.

Current-team logs are written under `logs/`. Player scrape runs write local
artifacts under `run_artifacts/player_runs/<run_id>/`, including `run.log`,
upload-ready JSONL files, and any structured error files. Generated logs and
run artifacts are intentionally ignored by Git.

## Local Setup

Install Python dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Install Playwright browsers if they are not already available:

```bash
python3 -m playwright install chromium
```

Create local secrets from the safe templates:

```bash
cp secrets/biwenger.example.toml secrets/biwenger.toml
cp secrets/supabase.example.toml secrets/supabase.toml
```

Fill in `secrets/biwenger.toml` with both Biwenger credential profiles:

- `[biwenger]` is used for current-team extraction.
- `[biwenger_player_scraper]` is used for high-volume player scraping.

Fill in `secrets/supabase.toml` with the Supabase project URL and anon key.

The `secrets/` directory remains ignored by Git except for `*.example.toml`
templates. Do not commit real credentials. OpenAI, Gemini, and local Ollama
secrets are not required for the current Biwenger-only pipeline.

## Supabase Bootstrap

Normal scraping uses the Supabase project URL and anon key from
`secrets/supabase.toml`. Those credentials are for data upload only; they should
not create tables.

For a new Supabase project, apply the tracked schema migration once with the
Supabase CLI:

```bash
/opt/homebrew/bin/brew install supabase/tap/supabase
supabase --version
supabase init
supabase link --project-ref <your-project-ref>
supabase db push
```

The Supabase CLI is a system tool, not a Python package, so it is intentionally
not listed in `requirements.txt`.

Schema changes must be made as new timestamped SQL files under
`supabase/migrations/`. Do not edit already-pushed migrations or maintain a
separate schema snapshot SQL file.

After the migration is applied, verify the anon connection:

```bash
python3 -m supabase_client.connection
```

If the normal pipeline runs before the migration exists, it should fail with a
clear message telling you to run the schema bootstrap first.

The active Biwenger table semantics are documented in
`docs/supabase_table_contracts.md`. Use that document when changing persistence
or planning dashboard queries.

## Local Verification

Start with unit tests because they do not need Biwenger, Playwright, or
Supabase:

```bash
make ci
make test
make lint
make format-check
```

`make ci` is the default local pre-commit check for normal code, parser,
persistence, and documentation changes. It runs Ruff linting, Ruff formatting
checks, and pytest without external services.

For browser verification, headed dry-runs are the default safe mode. They log in,
scrape, print samples, checkpoint player outputs locally, and do not write to
Supabase:

```bash
make dry-run-players-2
make dry-run-player-kita
make dry-run-player-mbappe
make dry-run-team
```

Use `make dry-run-players-15` before merging riskier player selector,
navigation, timing, or parser changes. Use `make dry-run-ladder` for the basic
player checks, and `make dry-run-ladder-broad` when you also want current-team
and the 15-player smoke test.

Supabase write tests should only be run after dry-run output looks correct and
the user explicitly approves writing rows:

```bash
make write-players-2
make upload-checkpoint CHECKPOINT_DIR=run_artifacts/player_runs/<run_id>
```

`write-players-2` performs a small headed scrape and writes to Supabase.
`upload-checkpoint` skips Biwenger entirely and uploads rows already saved in a
checkpoint run folder.

## Local Scheduling

macOS scheduling is handled with LaunchAgents that call repo-owned scripts:

```bash
bash bash_scripts/run_current_team.sh
bash bash_scripts/run_players.sh
```

The jobs are intentionally separate because current-team and player scraping use
different credentials, runtime profiles, and recovery behavior. The player
script runs headed, checkpoints every player, uploads in batches of 10, and
retries first-pass failures for the top 150 selected players by default.

LaunchAgent templates live under `launchd/` and run daily at 10:00 by default:

```text
launchd/com.biwenger.current-team.plist.example
launchd/com.biwenger.players.plist.example
```

Setup, manual trigger, notification checks, temporary 2-player scheduler tests,
and log inspection are documented in `launchd/launchagent_test_guide.md`.

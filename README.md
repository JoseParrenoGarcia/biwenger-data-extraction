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

- `[biwenger]` is the personal account and is used for current-team extraction only.
- `[biwenger_player_scraper]` is the dedicated scraper/test account and is used
  for high-volume player scraping.

The player pipeline has a code guardrail to avoid accidentally running bulk
scraping with the personal `[biwenger]` profile.

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
make run-players-ui
make run-players-ui-popup
make run-players-ui-write-2
make run-players-ui-popup-write-2
make dry-run-players-2
make dry-run-player-kita
make dry-run-player-mbappe
make dry-run-player-marc-roca
make dry-run-player-gueye
make dry-run-team
```

Use `make dry-run-players-15` before merging riskier player selector,
navigation, timing, or parser changes. Use `make dry-run-ladder` for the basic
player checks, `make dry-run-player-regressions` for targeted known-problem
players, and `make dry-run-ladder-broad` when you also want current-team and
the 15-player smoke test.

`make run-players-ui` launches the same safe 2-player dry-run but with the new
live terminal dashboard. This UI is intended for manual interactive runs only;
scheduled jobs should keep relying on `run.log` and checkpoint artifacts.
`make run-players-ui-popup` opens that same UI run in a separate macOS Terminal
window, which is handy if you want to leave it floating while keeping your
current shell free.
`make run-players-ui-write-2` runs the same UI flow but writes the 2-player
sample to Supabase, and `make run-players-ui-full` is the full headed UI write
run for production-style manual usage.
The popup equivalents are `make run-players-ui-popup-write-2` and
`make run-players-ui-popup-full`.

Recommended player dry-run scenarios:

- `kazunari-kita`: no-round / sparse-data case.
- `mbappe`: healthy high-signal baseline with full data.
- `marc-roca`: previously failed in list-driven flow but succeeded in direct
  slug mode; useful for Points-tab readiness and navigation regressions.
- `maguette-gueye`: scoring-system menu timeout variant.

Supabase write tests should only be run after dry-run output looks correct and
the user explicitly approves writing rows:

```bash
make write-players-2
make run-players-ui-write-2
make run-players-ui-full
make upload-checkpoint CHECKPOINT_DIR=run_artifacts/player_runs/<run_id>
```

`write-players-2` performs a small headed scrape and writes to Supabase.
`run-players-ui-write-2` does the same with the live UI, and
`run-players-ui-full` is the full headed UI write command.
`upload-checkpoint` skips Biwenger entirely and uploads rows already saved in a
checkpoint run folder.

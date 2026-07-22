# Supabase Table Contracts

Date: 2026-07-20

This document describes the semantic contract for the active Biwenger tables.
Supabase migrations are the only executable schema source of truth. This
document is the human-facing contract for agents and future dashboard work.

Runtime scraping must not perform DDL. Apply schema changes through
`supabase/migrations/` with `supabase db push`.

## Persistence Ownership

Generic Supabase primitives live in `supabase_client/`:

- connection setup;
- table-existence checks;
- generic insert/upsert helpers.

Biwenger table semantics live with the owning pipeline:

- `scraping_biwenger/current_team/persist.py`
- `scraping_biwenger/current_team/repository.py`
- `scraping_biwenger/players/persist.py`
- `scraping_biwenger/players/repository.py`

Do not add Biwenger-specific delete, identity, or delta logic to
`supabase_client/utils.py`.

## `biwenger_current_team`

Purpose: current squad snapshot for the personal Biwenger team.

Semantic grain: one row per player currently shown in the user's squad table.
This is current state, not history.

Write behavior:

- validate outgoing dataframe columns;
- delete all existing rows;
- insert the freshly scraped squad rows.

Important identity notes:

- No historical uniqueness is required because the table is replaced every run.
- `player_slug` and `player_url` are useful stable identifiers when present,
  but they are not used to append history.
- Dashboard consumers should treat this table as "latest owned squad".

Schema source:

- Created by `supabase/migrations/20260718161000_biwenger_init.sql`.
- Extended by `supabase/migrations/20260718174500_extend_current_team_snapshot.sql`.

## `biwenger_player_stats`

Purpose: daily player-level stats snapshot from the player detail panel.

Semantic grain: one row per player, scoring system, and scrape date.

Current identity:

`slug + as_of_date + scoring_system`

Write behavior:

- validate outgoing stats/matches/value dataframe columns together;
- delete the existing row for the same current identity;
- insert the latest scraped row.

Important semantics:

- `season` is the Biwenger season label visible in the player detail page.
- `as_of_date` is the scraper run date, not the season start date.
- Stats are snapshots. If a player's points or market percentages change later
  on the same scrape date, the latest write replaces that date's row.
- Historical analysis across dates should use `as_of_date`.
- Historical analysis across seasons should also use `season` once the dashboard
  layer needs season-aware summaries.

Database protection:

- Unique partial index on `(slug, as_of_date, scoring_system)` where slug is
  present.

## `biwenger_player_matches`

Purpose: per-player match history shown on the Points tab.

Semantic grain: one row per player, season, round, match date, and scoring
system.

Current identity:

```text
slug + season_label + round_label + match_date + scoring_system
```

Preferred future identity once scraped:

```text
slug + season_label + match_id + scoring_system
```

Write behavior:

- transform dedupes incoming rows by the season-aware identity and keeps the
  latest incoming row;
- persistence deletes only matching season-aware identities before insert;

Important semantics:

- `season_label` comes from Biwenger's selected season, for example
  `2025/2026`.
- `round_label` is the visible round code, for example `R1`.
- `match_date` is the match date, not the scrape date.
- `as_of_date` is retained for audit/debug context, but it is not part of the
  preferred match identity.
- Mutable scraped fields such as `points`, `best_xi`, and `events` are not part
  of the duplicate key. Replaying a checkpoint updates the row for the same
  match identity instead of creating a duplicate.
- If a new season starts with no match rows, the player can still have a stats
  row while this table correctly has zero match rows for that player/season
  until Biwenger exposes match history.

Database protection:

- Unique partial index on
  `(slug, season_label, round_label, match_date, scoring_system)` where all key
  fields are present.
- Supporting lookup index on `(slug, match_date, scoring_system)`.

Known cleanup:

- Add `match_id` once the parser captures match URLs consistently, then migrate
  the preferred identity to `slug + season_label + match_id + scoring_system`.

## `biwenger_player_value`

Purpose: player market value history from the Value tab CSV export.

Semantic grain: one row per player slug and value date.

Current identity:

```text
slug + date
```

Write behavior:

- fetch existing value rows for the same slug and date range;
- insert dates that do not already exist;
- delete and reinsert dates where `market_value_eur` changed;
- skip unchanged rows.

Important semantics:

- `date` is the market-value observation date from the CSV.
- This table is append-mostly historical data.
- `player_name` and `team` are descriptive context captured at scrape time and
  may change over a player's career. Dashboard consumers should use `slug` as
  the stable player identity.

Database protection:

- Unique constraint on `(slug, date)`.

## Checkpoint Replay

Player checkpoints under `run_artifacts/player_runs/<run_id>/` contain
normalized, upload-ready rows:

- `player_stats.jsonl`
- `player_matches.jsonl`
- `player_values.jsonl`

Replay with:

```bash
.venv/bin/python -m scraping_biwenger.get_player_stats --upload-checkpoint run_artifacts/player_runs/<run_id>
```

Replay should be idempotent under the table identities above. If replay creates
duplicates, the table contract or persistence identity has drifted and should be
fixed before running larger production uploads.

## Migration And Reference Policy

Executable schema changes belong only in new timestamped files under
`supabase/migrations/`.

Do not edit historical migrations after they have been pushed to Supabase.
Create a follow-up migration instead, then update this contract document when
the active table semantics change. The repo intentionally does not maintain a
separate schema snapshot SQL file.

-- Extend current-team snapshots with stable row metadata from the Biwenger squad table.

alter table public.biwenger_current_team
    add column if not exists position_short text,
    add column if not exists position text,
    add column if not exists team_name text,
    add column if not exists player_slug text,
    add column if not exists player_url text,
    add column if not exists previous_season_points integer,
    add column if not exists home_points integer not null default 0,
    add column if not exists home_average_points double precision not null default 0,
    add column if not exists away_points integer not null default 0,
    add column if not exists away_average_points double precision not null default 0,
    add column if not exists next_fixture_location text,
    add column if not exists next_opponent text,
    add column if not exists next_match_url text,
    add column if not exists next_match_id bigint;

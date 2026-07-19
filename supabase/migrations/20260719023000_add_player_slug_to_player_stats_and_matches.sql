-- Add Biwenger URL slugs to player stats and match rows.
-- Existing rows are left nullable until a separate backfill is run.

alter table public.biwenger_player_stats
    add column if not exists slug text;

alter table public.biwenger_player_matches
    add column if not exists slug text;

drop index if exists public.biwenger_player_stats_snapshot_scoring_uidx;

create unique index if not exists biwenger_player_stats_slug_snapshot_scoring_uidx
    on public.biwenger_player_stats (slug, as_of_date, scoring_system)
    where slug is not null and btrim(slug) <> '';

create unique index if not exists biwenger_player_stats_legacy_snapshot_scoring_uidx
    on public.biwenger_player_stats (player_name, team, as_of_date, scoring_system)
    where slug is null or btrim(slug) = '';

create index if not exists biwenger_player_matches_slug_match_date_scoring_idx
    on public.biwenger_player_matches (slug, match_date, scoring_system)
    where slug is not null and btrim(slug) <> '';

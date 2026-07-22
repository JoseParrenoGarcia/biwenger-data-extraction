-- Make player stats and player matches fully upsert-ready for issue #90.
-- PostgREST on_conflict requires a non-partial unique target.

with ranked as (
    select
        id,
        row_number() over (
            partition by slug, as_of_date, scoring_system
            order by created_at desc nulls last, id desc
        ) as duplicate_rank
    from public.biwenger_player_stats
)
delete from public.biwenger_player_stats stats
using ranked
where stats.id = ranked.id
  and ranked.duplicate_rank > 1;

with ranked as (
    select
        id,
        row_number() over (
            partition by slug, season_label, round_label, match_date, scoring_system
            order by created_at desc nulls last, id desc
        ) as duplicate_rank
    from public.biwenger_player_matches
)
delete from public.biwenger_player_matches matches
using ranked
where matches.id = ranked.id
  and ranked.duplicate_rank > 1;

alter table public.biwenger_player_stats
    alter column slug set not null,
    alter column as_of_date set not null,
    alter column scoring_system set not null;

alter table public.biwenger_player_matches
    alter column slug set not null,
    alter column season_label set not null,
    alter column round_label set not null,
    alter column match_date set not null,
    alter column scoring_system set not null;

drop index if exists public.biwenger_player_stats_slug_snapshot_scoring_uidx;
create unique index if not exists biwenger_player_stats_slug_snapshot_scoring_uidx
    on public.biwenger_player_stats (slug, as_of_date, scoring_system);

drop index if exists public.biwenger_player_matches_slug_season_round_date_scoring_uidx;
create unique index if not exists biwenger_player_matches_slug_season_round_date_scoring_uidx
    on public.biwenger_player_matches (
        slug,
        season_label,
        round_label,
        match_date,
        scoring_system
    );

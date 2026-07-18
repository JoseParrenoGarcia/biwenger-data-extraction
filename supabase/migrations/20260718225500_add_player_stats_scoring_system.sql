-- Track scoring-dependent player stats and match points.

alter table public.biwenger_player_stats
    add column if not exists scoring_system text;

alter table public.biwenger_player_matches
    add column if not exists scoring_system text;

update public.biwenger_player_stats
set scoring_system = 'unknown'
where scoring_system is null;

update public.biwenger_player_matches
set scoring_system = 'unknown'
where scoring_system is null;

alter table public.biwenger_player_stats
    alter column scoring_system set default 'sofascore',
    alter column scoring_system set not null;

alter table public.biwenger_player_matches
    alter column scoring_system set default 'sofascore',
    alter column scoring_system set not null;

with ranked as (
    select
        id,
        row_number() over (
            partition by player_name, team, as_of_date, scoring_system
            order by created_at desc nulls last, id desc
        ) as duplicate_rank
    from public.biwenger_player_stats
)
delete from public.biwenger_player_stats stats
using ranked
where stats.id = ranked.id
  and ranked.duplicate_rank > 1;

create unique index if not exists biwenger_player_stats_snapshot_scoring_uidx
    on public.biwenger_player_stats (player_name, team, as_of_date, scoring_system);

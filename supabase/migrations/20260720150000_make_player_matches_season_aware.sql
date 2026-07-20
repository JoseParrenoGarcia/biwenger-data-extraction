-- Make player match duplicate protection season-aware using fields already scraped today.
-- Preferred future identity once scraped: slug + season_label + match_id + scoring_system.

with ranked as (
    select
        id,
        row_number() over (
            partition by slug, season_label, round_label, match_date, scoring_system
            order by created_at desc nulls last, id desc
        ) as duplicate_rank
    from public.biwenger_player_matches
    where slug is not null
      and btrim(slug) <> ''
      and season_label is not null
      and round_label is not null
      and match_date is not null
      and scoring_system is not null
)
delete from public.biwenger_player_matches matches
using ranked
where matches.id = ranked.id
  and ranked.duplicate_rank > 1;

create unique index if not exists biwenger_player_matches_slug_season_round_date_scoring_uidx
    on public.biwenger_player_matches (
        slug,
        season_label,
        round_label,
        match_date,
        scoring_system
    )
    where slug is not null
      and btrim(slug) <> ''
      and season_label is not null
      and round_label is not null
      and match_date is not null
      and scoring_system is not null;

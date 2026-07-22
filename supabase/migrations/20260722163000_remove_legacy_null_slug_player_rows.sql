-- Finalize issue #93 by removing legacy null-slug player rows.
-- Slugged stats and match rows are now the canonical dataset.

delete from public.biwenger_player_stats
where slug is null
   or btrim(slug) = '';

delete from public.biwenger_player_matches
where slug is null
   or btrim(slug) = '';

drop index if exists public.biwenger_player_stats_legacy_snapshot_scoring_uidx;
drop index if exists public.biwenger_player_stats_snapshot_scoring_uidx;

-- Enable RLS on the exposed Biwenger tables.
-- Runtime scraper writes and dashboard reads are expected to use a server-only key.

alter table public.biwenger_current_team enable row level security;
alter table public.biwenger_player_stats enable row level security;
alter table public.biwenger_player_matches enable row level security;
alter table public.biwenger_player_value enable row level security;

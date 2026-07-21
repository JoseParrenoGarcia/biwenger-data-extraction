from scraping_biwenger.players.detail_loop import scrape_all_players_detail
from scraping_biwenger.players.discover import extract_all_player_names
from scraping_biwenger.shared.auth import dismiss_app_popups_if_present
from scraping_biwenger.shared.navigation import click_tab_in_horizontal_main_menu
from scraping_biwenger.shared.timing import _rand_sleep

RETRYABLE_DETAIL_ERROR_STAGES = {
    "open_player",
    "select_scoring_system",
    "scrape_detail",
}


def select_player_table_layout(page, logger=None) -> None:
    """
    Navigate to the players tab and select table layout.
    """
    click_tab_in_horizontal_main_menu(page, "players", logger=logger)
    dismiss_app_popups_if_present(page, logger=logger)
    _rand_sleep(0.5, 1.5)

    try:
        page.get_by_role("button", name="Table").click()
        if logger:
            logger.info("Selected players table layout.")
    except Exception:
        if logger:
            logger.info("Players table layout button was not clicked; scraper will wait for rows.")
    _rand_sleep(0.5, 1.5)


def scrape_player_rows(
    page,
    logger,
    *,
    max_pages: int | None = None,
    max_players_detail: int | None = None,
    player_slug: str | None = None,
    retry_top_players: int = 0,
    on_player_payload=None,
    on_player_error=None,
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """
    Scrape player discovery rows plus detail, match, and value-history rows.
    """
    if player_slug:
        slug = player_slug.strip().strip("/")
        if "/" in slug:
            slug = slug.rstrip("/").split("/")[-1]
        selected_players = [
            {
                "name": slug,
                "slug": slug,
                "href": f"/la-liga/players/{slug}",
                "open_by_href_only": True,
                "rank": 1,
                "attempt": "initial",
            }
        ]
        if logger:
            logger.info(
                "Targeting one player by slug '%s'; skipping player-list discovery.",
                slug,
            )
        players_list = selected_players
    else:
        select_player_table_layout(page, logger=logger)

        players_list = extract_all_player_names(
            logger=logger,
            page=page,
            max_pages=max_pages,
            max_players=max_players_detail,
        )
        if max_players_detail is not None:
            selected_players = players_list[:max_players_detail]
        else:
            selected_players = players_list
        selected_players = [
            {
                **player,
                "rank": idx,
                "attempt": "initial",
            }
            for idx, player in enumerate(selected_players, start=1)
        ]

        if logger:
            logger.info(
                "Discovered %s players and selected %s for detail scraping.",
                len(players_list),
                len(selected_players),
            )

    if not selected_players:
        return players_list, [], [], []

    retry_candidates: dict[str, dict] = {}

    def player_retry_key(player: dict) -> str:
        return player.get("slug") or player.get("href") or player.get("name", "")

    def should_retry_player(player: dict, stage: str) -> bool:
        if retry_top_players <= 0:
            return False
        if player.get("attempt") != "initial":
            return False
        if stage not in RETRYABLE_DETAIL_ERROR_STAGES:
            return False
        rank = player.get("rank")
        if not isinstance(rank, int) or rank > retry_top_players:
            return False
        return True

    def handle_player_error(*, player, stage, message) -> None:
        if on_player_error:
            on_player_error(player=player, stage=stage, message=message)
        if not should_retry_player(player, stage):
            return
        key = player_retry_key(player)
        if not key or key in retry_candidates:
            return
        retry_candidates[key] = {
            **player,
            "attempt": "retry",
            "open_by_href_only": True,
            "retry_stage": stage,
        }
        if logger:
            logger.info(
                "Queued player for retry: %s rank=%s stage=%s",
                player.get("name", ""),
                player.get("rank"),
                stage,
            )

    player_detail_rows, match_rows, value_history_rows = scrape_all_players_detail(
        logger,
        page,
        selected_players,
        max_players=max_players_detail,
        collect_matches=True,
        on_player_payload=on_player_payload,
        on_player_error=handle_player_error,
    )

    if retry_candidates:
        retry_players = list(retry_candidates.values())
        if logger:
            logger.info(
                "Starting retry pass for %s failed top-%s players.",
                len(retry_players),
                retry_top_players,
            )
        retry_detail_rows, retry_match_rows, retry_value_history_rows = scrape_all_players_detail(
            logger,
            page,
            retry_players,
            max_players=len(retry_players),
            collect_matches=True,
            on_player_payload=on_player_payload,
            on_player_error=on_player_error,
        )
        player_detail_rows.extend(retry_detail_rows)
        match_rows.extend(retry_match_rows)
        value_history_rows.extend(retry_value_history_rows)
        if logger:
            recovered = len(retry_detail_rows)
            failed = max(0, len(retry_players) - recovered)
            logger.info(
                "Retry pass completed: %s recovered players, %s still failed.",
                recovered,
                failed,
            )

    return players_list, player_detail_rows, match_rows, value_history_rows

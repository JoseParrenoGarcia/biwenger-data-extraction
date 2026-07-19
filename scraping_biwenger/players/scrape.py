from scraping_biwenger.helper_extract_all_player_names import extract_all_player_names
from scraping_biwenger.helper_pipeline_loop import scrape_all_players_detail
from scraping_biwenger.scraper_actions_in_biwenger import click_tab_in_horizontal_main_menu
from scraping_biwenger.utils import _rand_sleep


def select_player_table_layout(page, logger=None) -> None:
    """
    Navigate to the players tab and select table layout.
    """
    click_tab_in_horizontal_main_menu(page, "players", logger=logger)
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
            }
        ]
        if logger:
            logger.info(
                "Targeting one player by slug '%s'; skipping player-list discovery.",
                slug,
            )
        player_detail_rows, match_rows, value_history_rows = scrape_all_players_detail(
            logger,
            page,
            selected_players,
            max_players=1,
            collect_matches=True,
        )
        return selected_players, player_detail_rows, match_rows, value_history_rows

    select_player_table_layout(page, logger=logger)

    players_list = extract_all_player_names(
        logger=logger,
        page=page,
        max_pages=max_pages,
    )
    if max_players_detail is not None:
        selected_players = players_list[:max_players_detail]
    else:
        selected_players = players_list

    if logger:
        logger.info(
            "Discovered %s players and selected %s for detail scraping.",
            len(players_list),
            len(selected_players),
        )

    if not selected_players:
        return players_list, [], [], []

    player_detail_rows, match_rows, value_history_rows = scrape_all_players_detail(
        logger,
        page,
        selected_players,
        max_players=max_players_detail,
        collect_matches=True,
    )
    return players_list, player_detail_rows, match_rows, value_history_rows

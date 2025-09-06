from config_logging import get_logger
from scraping_biwenger.scraper_actions_in_biwenger import (
    load_biwenger_credentials,
    start_browser_accept_cookies,
    perform_login,
    click_tab_in_horizontal_main_menu,
)
from scraping_biwenger.helper_extract_all_player_names import extract_all_player_names
from scraping_biwenger.helper_pipeline_loop import scrape_all_players_detail
from scraping_biwenger.utils import _rand_sleep
import pandas as pd
from supabase_client.connection import get_supabase_client
from supabase_client.utils import (
    check_if_table_exists,
    insert_rows_into_table,
    insert_rows_into_table_batched,
    delete_rows_for_slug_dates,
    fetch_existing_values_for_slug,
)


def ETL_get_player_stats(max_pages=100, max_players_detail=1_000):
    """
    ETL: Login to Biwenger, scrape player stats, and (later) upload to Supabase.
    """
    logger = get_logger(
        "ETL_get_player_stats",
        log_file="logs/ETL_get_player_stats.log"
    )
    logger.info("=" * 70)
    logger.info("🚀 Starting ETL: get_player_stats")
    logger.info("=" * 70)

    # 1) Load credentials (from secrets/biwenger.toml)
    creds = load_biwenger_credentials(profile="biwenger_player_scraper")
    logger.info("✅ Credentials loaded successfully.")

    # 2) Start browser
    pw, browser, context, page = start_browser_accept_cookies(headless=True)
    logger.info("✅ Logged in")

    # 3) Login
    try:
        perform_login(page, creds["email"], creds["password"])

        # 4) Navigate to players page
        click_tab_in_horizontal_main_menu(page, "players")
        _rand_sleep(0.5, 1.5)

        # 5) Click view as list
        page.get_by_role("button", name="Table").click()
        _rand_sleep(0.5, 1.5)

        # 6) Extract all player names
        players_list = extract_all_player_names(logger=logger, page=page, max_pages=max_pages)
        # print(players_list)

        if not players_list:
            logger.warning("No players extracted; aborting search step.")
            return

        # 7) Extract details (stats) + per-match rows in the same pass
        player_detail_rows, match_rows, value_history_rows = scrape_all_players_detail(
            logger, page, players_list, max_players=max_players_detail, collect_matches=True
        )

        # --- Stats DF (left panel) ---
        player_detail_df = (
            pd.DataFrame(player_detail_rows)
            .drop_duplicates(subset=["player_name"], keep="first")
            .drop(columns=["name", "slug", "href"], errors="ignore")
        )

        # --- Matches DF (right panel, 'Points' tab) ---
        matches_df = pd.DataFrame(match_rows)
        keep_cols = ["season_label", "round_label", "match_date", "points", "best_xi", "events", "player_name", "team"]
        matches_df = matches_df[[c for c in keep_cols if c in matches_df.columns]].copy()

        # --- Value DF (right panel, 'Value' tab) ---
        value_history_df = pd.DataFrame(value_history_rows)
        # print(value_history_df)

        # 8) Save to Supabase
        supabase = get_supabase_client()

        # Upsert players first (to get their IDs)
        table_name = "biwenger_player_stats"

        if not check_if_table_exists(supabase, table_name):
            logger.error(f"❌ Table '{table_name}' does not exist in Supabase.")
        else:
            # Delete everything first (truncate semantics)
            supabase.table(table_name).delete().neq("id", 0).execute()
            logger.info(f"🗑️ Cleared existing rows from '{table_name}'")

            # Insert fresh rows
            insert_rows_into_table(supabase, table_name=table_name, rows=player_detail_df.to_dict(orient="records"))
            logger.info(f"✅ Inserted {len(player_detail_rows)} rows into '{table_name}'")

        # Upsert matches
        matches_table = "biwenger_player_matches"
        if not check_if_table_exists(supabase, matches_table):
            logger.error(f"❌ Table '{matches_table}' does not exist in Supabase.")
        else:
            supabase.table(matches_table).delete().neq("id", 0).execute()
            logger.info(f"🗑️ Cleared existing rows from '{matches_table}'")
            insert_rows_into_table(supabase, table_name=matches_table, rows=matches_df.to_dict(orient="records"))
            logger.info(f"✅ Inserted {len(matches_df)} rows into '{matches_table}'")

        # --- Value DF (right panel, 'Value' tab) ---
        value_history_df = pd.DataFrame(value_history_rows)

        v = value_history_df.copy()
        v["date"] = pd.to_datetime(v["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        v["market_value_eur"] = pd.to_numeric(v["market_value_eur"], errors="coerce")
        v = v.dropna(subset=["date", "market_value_eur"])

        to_insert_all = []

        for slug, g in v.groupby("slug"):
            if not slug: continue
            min_d, max_d = g["date"].min(), g["date"].max()

            existing = fetch_existing_values_for_slug(supabase, "biwenger_player_value", slug, min_d, max_d)
            # map date -> value in DB
            db_map = dict(zip(existing["date"], existing["market_value_eur"]))

            # split new vs changed
            g = g.sort_values("date").drop_duplicates(subset=["date"], keep="last")
            new_mask = ~g["date"].isin(existing["date"])
            changed_mask = g["date"].isin(existing["date"]) & (g["market_value_eur"] != g["date"].map(db_map))

            new_rows = g.loc[new_mask]
            changed_rows = g.loc[changed_mask]

            # remove the changed ones in DB, then insert them with the new value
            if not changed_rows.empty:
                delete_rows_for_slug_dates(
                    supabase,
                    "biwenger_player_value",
                    slug,
                    changed_rows["date"].tolist()
                )
                to_insert_all.append(changed_rows)

            if not new_rows.empty:
                to_insert_all.append(new_rows)

        # bulk insert everything we need (JSON-safe)
        if to_insert_all:
            payload_df = pd.concat(to_insert_all, ignore_index=True)
            payload_df = payload_df.where(payload_df.notna(), None)
            insert_rows_into_table_batched(
                supabase,
                "biwenger_player_value",
                payload_df.to_dict(orient="records"),
                chunk_size=1000,
                sleep_s=0.03,
                returning="minimal",
            )

    finally:
        try:
            context.close()
        except Exception:
            pass
        try:
            browser.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass

if __name__ == "__main__":
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', None)

    ETL_get_player_stats()

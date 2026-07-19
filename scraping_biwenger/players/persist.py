import pandas as pd

from supabase_client.connection import get_supabase_client
from supabase_client.utils import (
    check_if_table_exists,
    delete_matches_for_player_dates,
    delete_rows_for_slug_dates,
    delete_stats_for_player_team_day,
    fetch_existing_values_for_slug,
    insert_rows_into_table_batched,
)

from scraping_biwenger.players.transform import validate_player_payloads


PLAYER_STATS_TABLE = "biwenger_player_stats"
PLAYER_MATCHES_TABLE = "biwenger_player_matches"
PLAYER_VALUE_TABLE = "biwenger_player_value"
PLAYER_TABLES = [
    PLAYER_STATS_TABLE,
    PLAYER_MATCHES_TABLE,
    PLAYER_VALUE_TABLE,
]


def _optional_text(value):
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def missing_table_message(table_names: list[str]) -> str:
    quoted = ", ".join(f"'{name}'" for name in table_names)
    return (
        f"Supabase player table(s) missing: {quoted}. "
        "Run `supabase db push` before uploading player data."
    )


def assert_player_tables_exist(supabase, logger=None) -> None:
    missing = [table_name for table_name in PLAYER_TABLES if not check_if_table_exists(supabase, table_name)]
    if missing:
        message = missing_table_message(missing)
        if logger:
            logger.error(message)
        raise RuntimeError(message)


def persist_player_outputs(
    stats_df: pd.DataFrame,
    matches_df: pd.DataFrame,
    value_history_df: pd.DataFrame,
    *,
    logger=None,
    supabase=None,
) -> None:
    """
    Persist player stats, match rows, and market value history.
    """
    validate_player_payloads(stats_df, matches_df, value_history_df)
    supabase = supabase or get_supabase_client()
    assert_player_tables_exist(supabase, logger=logger)

    persist_player_stats(stats_df, supabase=supabase, logger=logger)
    persist_player_matches(matches_df, supabase=supabase, logger=logger)
    persist_player_values(value_history_df, supabase=supabase, logger=logger)


def persist_player_stats(stats_df: pd.DataFrame, *, supabase, logger=None) -> None:
    if stats_df.empty:
        if logger:
            logger.info("No player stats to process.")
        return

    for pname, team, slug, as_of_date, scoring_system in (
        stats_df[["player_name", "team", "slug", "as_of_date", "scoring_system"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    ):
        delete_stats_for_player_team_day(
            supabase,
            PLAYER_STATS_TABLE,
            pname,
            team,
            as_of_date,
            _optional_text(scoring_system),
            _optional_text(slug),
        )

    payload = stats_df.astype(object).where(stats_df.notna(), None).to_dict(orient="records")
    insert_rows_into_table_batched(
        supabase,
        table_name=PLAYER_STATS_TABLE,
        rows=payload,
        chunk_size=1000,
        sleep_s=0.03,
        returning="minimal",
    )
    if logger:
        logger.info("Upserted %s player stat rows into '%s'.", len(payload), PLAYER_STATS_TABLE)


def persist_player_matches(matches_df: pd.DataFrame, *, supabase, logger=None) -> None:
    if matches_df.empty:
        if logger:
            logger.info("No match rows to insert.")
        return

    to_insert = []
    for (pname, team, slug, scoring_system), group in matches_df.groupby(
        ["player_name", "team", "slug", "scoring_system"],
        dropna=False,
    ):
        dates = group["match_date"].dropna().unique().tolist()
        if not dates:
            continue

        delete_matches_for_player_dates(
            supabase,
            PLAYER_MATCHES_TABLE,
            pname,
            team,
            dates,
            _optional_text(scoring_system),
            _optional_text(slug),
        )
        to_insert.append(group)

    if not to_insert:
        if logger:
            logger.info("No match rows had dates to insert.")
        return

    payload_df = pd.concat(to_insert, ignore_index=True)
    payload_df = payload_df.astype(object).where(payload_df.notna(), None)
    insert_rows_into_table_batched(
        supabase,
        table_name=PLAYER_MATCHES_TABLE,
        rows=payload_df.to_dict(orient="records"),
        chunk_size=1000,
        sleep_s=0.03,
        returning="minimal",
    )
    if logger:
        logger.info("Upserted %s match rows into '%s'.", len(payload_df), PLAYER_MATCHES_TABLE)


def persist_player_values(value_history_df: pd.DataFrame, *, supabase, logger=None) -> None:
    if value_history_df.empty:
        if logger:
            logger.info("No value history rows to process.")
        return

    to_insert_all = []

    for slug, group in value_history_df.groupby("slug"):
        if not slug:
            continue
        min_d = group["date"].min()
        max_d = group["date"].max()
        existing = fetch_existing_values_for_slug(
            supabase,
            PLAYER_VALUE_TABLE,
            slug,
            min_d,
            max_d,
        )
        db_map = dict(zip(existing["date"], existing["market_value_eur"]))

        group = group.sort_values("date").drop_duplicates(subset=["date"], keep="last")
        new_mask = ~group["date"].isin(existing["date"])
        changed_mask = group["date"].isin(existing["date"]) & (
            group["market_value_eur"] != group["date"].map(db_map)
        )

        changed_rows = group.loc[changed_mask]
        if not changed_rows.empty:
            delete_rows_for_slug_dates(
                supabase,
                PLAYER_VALUE_TABLE,
                slug,
                changed_rows["date"].tolist(),
            )
            to_insert_all.append(changed_rows)

        new_rows = group.loc[new_mask]
        if not new_rows.empty:
            to_insert_all.append(new_rows)

    if not to_insert_all:
        if logger:
            logger.info("No new or changed value history rows to insert.")
        return

    payload_df = pd.concat(to_insert_all, ignore_index=True)
    payload_df = payload_df.astype(object).where(payload_df.notna(), None)
    insert_rows_into_table_batched(
        supabase,
        PLAYER_VALUE_TABLE,
        payload_df.to_dict(orient="records"),
        chunk_size=1000,
        sleep_s=0.03,
        returning="minimal",
    )
    if logger:
        logger.info("Inserted %s new or changed value history rows into '%s'.", len(payload_df), PLAYER_VALUE_TABLE)

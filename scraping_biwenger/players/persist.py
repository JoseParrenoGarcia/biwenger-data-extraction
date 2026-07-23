import pandas as pd

from scraping_biwenger.players.repository import (
    delete_value_history_dates,
    fetch_existing_value_history,
    insert_player_rows_batched,
    player_table_exists,
)
from scraping_biwenger.players.transform import validate_player_payloads
from supabase_client.connection import get_supabase_admin_client
from supabase_client.utils import upsert_rows_into_table_batched

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


def _assert_non_empty_slugs(df: pd.DataFrame, *, frame_name: str) -> None:
    if df.empty:
        return
    slug_series = df["slug"].map(_optional_text)
    if slug_series.isna().any():
        raise ValueError(f"{frame_name} payload contains rows without slug; slug is required for persistence.")


def _assert_non_empty_identity_values(df: pd.DataFrame, *, frame_name: str, columns: list[str]) -> None:
    if df.empty:
        return
    missing_columns = []
    for column in columns:
        series = df[column].map(_optional_text)
        if series.isna().any():
            missing_columns.append(column)
    if missing_columns:
        raise ValueError(
            f"{frame_name} payload contains rows without required identity values: {', '.join(missing_columns)}."
        )


def missing_table_message(table_names: list[str]) -> str:
    quoted = ", ".join(f"'{name}'" for name in table_names)
    return f"Supabase player table(s) missing: {quoted}. Run `supabase db push` before uploading player data."


def assert_player_tables_exist(supabase, logger=None) -> None:
    missing = [table_name for table_name in PLAYER_TABLES if not player_table_exists(supabase, table_name)]
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
    validate_player_payloads(
        stats_df,
        matches_df,
        value_history_df,
        require_slugs_for_persistence=True,
    )
    supabase = supabase or get_supabase_admin_client()
    assert_player_tables_exist(supabase, logger=logger)

    persist_player_stats(stats_df, supabase=supabase, logger=logger)
    persist_player_matches(matches_df, supabase=supabase, logger=logger)
    persist_player_values(value_history_df, supabase=supabase, logger=logger)


def persist_player_stats(stats_df: pd.DataFrame, *, supabase, logger=None) -> None:
    if stats_df.empty:
        if logger:
            logger.info("No player stats to process.")
        return

    _assert_non_empty_slugs(stats_df, frame_name="stats")
    _assert_non_empty_identity_values(
        stats_df,
        frame_name="stats",
        columns=["slug", "as_of_date", "scoring_system"],
    )

    input_rows = len(stats_df)
    payload_df = stats_df.drop_duplicates(subset=["slug", "as_of_date", "scoring_system"], keep="last").copy()
    payload = payload_df.astype(object).where(payload_df.notna(), None).to_dict(orient="records")
    if logger:
        logger.info(
            "Stats upsert attempt: input_rows=%s deduped_rows=%s conflict=slug,as_of_date,scoring_system",
            input_rows,
            len(payload),
        )
    upsert_rows_into_table_batched(
        supabase,
        table_name=PLAYER_STATS_TABLE,
        rows=payload,
        on_conflict="slug,as_of_date,scoring_system",
    )
    if logger:
        logger.info("Upserted %s player stat rows into '%s'.", len(payload), PLAYER_STATS_TABLE)


def persist_player_matches(matches_df: pd.DataFrame, *, supabase, logger=None) -> None:
    if matches_df.empty:
        if logger:
            logger.info("No match rows to insert.")
        return

    _assert_non_empty_slugs(matches_df, frame_name="matches")
    _assert_non_empty_identity_values(
        matches_df,
        frame_name="matches",
        columns=["slug", "season_label", "round_label", "match_date", "scoring_system"],
    )
    input_rows = len(matches_df)
    payload_df = matches_df.drop_duplicates(
        subset=["slug", "season_label", "round_label", "match_date", "scoring_system"],
        keep="last",
    ).copy()
    payload_df = payload_df.astype(object).where(payload_df.notna(), None)
    if logger:
        logger.info(
            "Matches upsert attempt: input_rows=%s deduped_rows=%s conflict=slug,season_label,round_label,match_date,scoring_system",
            input_rows,
            len(payload_df),
        )
    upsert_rows_into_table_batched(
        supabase,
        table_name=PLAYER_MATCHES_TABLE,
        rows=payload_df.to_dict(orient="records"),
        on_conflict="slug,season_label,round_label,match_date,scoring_system",
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
        existing = fetch_existing_value_history(
            supabase,
            PLAYER_VALUE_TABLE,
            slug,
            min_d,
            max_d,
        )
        db_map = dict(zip(existing["date"], existing["market_value_eur"]))

        group = group.sort_values("date").drop_duplicates(subset=["date"], keep="last")
        new_mask = ~group["date"].isin(existing["date"])
        changed_mask = group["date"].isin(existing["date"]) & (group["market_value_eur"] != group["date"].map(db_map))

        changed_rows = group.loc[changed_mask]
        if not changed_rows.empty:
            delete_value_history_dates(
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
    insert_player_rows_batched(
        supabase,
        PLAYER_VALUE_TABLE,
        payload_df.to_dict(orient="records"),
    )
    if logger:
        logger.info("Inserted %s new or changed value history rows into '%s'.", len(payload_df), PLAYER_VALUE_TABLE)

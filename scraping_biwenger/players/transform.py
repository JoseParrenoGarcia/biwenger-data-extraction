import json

import pandas as pd


PLAYER_STATS_COLUMNS = [
    "player_name",
    "team",
    "position",
    "status",
    "status_detail",
    "scoring_system",
    "points",
    "value",
    "min_value",
    "max_value",
    "matches_played",
    "average",
    "market_purchases_pct",
    "market_sales_pct",
    "market_usage_pct",
    "season",
    "as_of_date",
]

PLAYER_MATCHES_COLUMNS = [
    "season_label",
    "round_label",
    "match_date",
    "points",
    "best_xi",
    "events",
    "player_name",
    "team",
    "scoring_system",
    "as_of_date",
]

PLAYER_VALUE_COLUMNS = [
    "slug",
    "player_name",
    "team",
    "date",
    "market_value_eur",
]

INTEGER_COLUMNS = [
    "points",
    "value",
    "min_value",
    "max_value",
    "matches_played",
]

FLOAT_COLUMNS = [
    "average",
    "market_purchases_pct",
    "market_sales_pct",
    "market_usage_pct",
]

OPTIONAL_TEXT_COLUMNS = [
    "position",
    "status",
    "status_detail",
    "scoring_system",
    "season",
]


def _empty_outputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        pd.DataFrame(columns=PLAYER_STATS_COLUMNS),
        pd.DataFrame(columns=PLAYER_MATCHES_COLUMNS),
        pd.DataFrame(columns=PLAYER_VALUE_COLUMNS),
    )


def _clean_text(value):
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _events_dedupe_key(value) -> str:
    try:
        return json.dumps(value, sort_keys=True)
    except TypeError:
        return str(value)


def transform_player_outputs(
    player_detail_rows: list[dict],
    match_rows: list[dict],
    value_history_rows: list[dict],
    *,
    as_of_date: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Normalize raw player scrape rows into the three Supabase payload shapes.
    """
    today = as_of_date or pd.Timestamp.utcnow().date().isoformat()

    if not player_detail_rows and not match_rows and not value_history_rows:
        return _empty_outputs()

    player_detail_df = pd.DataFrame(player_detail_rows)
    if player_detail_df.empty:
        stats_df = pd.DataFrame(columns=PLAYER_STATS_COLUMNS)
    else:
        player_detail_df = (
            player_detail_df
            .drop_duplicates(subset=["player_name"], keep="first")
            .drop(columns=["name", "slug", "href"], errors="ignore")
        )
        stats_df = player_detail_df.drop_duplicates(
            subset=["player_name", "team"],
            keep="last",
        ).copy()
        stats_df["as_of_date"] = today
        for column in PLAYER_STATS_COLUMNS:
            if column not in stats_df.columns:
                stats_df[column] = None
        stats_df = stats_df[PLAYER_STATS_COLUMNS]
        stats_df["player_name"] = stats_df["player_name"].astype(str).str.strip()
        stats_df["team"] = stats_df["team"].astype(str).str.strip()
        for column in OPTIONAL_TEXT_COLUMNS:
            stats_df[column] = stats_df[column].map(_clean_text)
        stats_df["scoring_system"] = stats_df["scoring_system"].fillna("sofascore")
        for column in INTEGER_COLUMNS:
            stats_df[column] = pd.to_numeric(stats_df[column], errors="coerce").fillna(0).astype(int)
        for column in FLOAT_COLUMNS:
            stats_df[column] = pd.to_numeric(stats_df[column], errors="coerce").fillna(0.0).astype(float)

    matches_df = pd.DataFrame(match_rows)
    if matches_df.empty:
        matches_df = pd.DataFrame(columns=PLAYER_MATCHES_COLUMNS)
    else:
        keep_cols = [c for c in PLAYER_MATCHES_COLUMNS if c != "as_of_date"]
        matches_df = matches_df[[c for c in keep_cols if c in matches_df.columns]].copy()
        matches_df["as_of_date"] = today
        for column in PLAYER_MATCHES_COLUMNS:
            if column not in matches_df.columns:
                matches_df[column] = None
        matches_df = matches_df[PLAYER_MATCHES_COLUMNS]
        matches_df["scoring_system"] = matches_df["scoring_system"].map(_clean_text).fillna("sofascore")
        matches_df["match_date"] = pd.to_datetime(matches_df["match_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        matches_df["points"] = pd.to_numeric(matches_df["points"], errors="coerce")
        matches_df["_events_dedupe_key"] = matches_df["events"].map(_events_dedupe_key)
        matches_df = matches_df.drop_duplicates(
            subset=[
                "player_name",
                "team",
                "match_date",
                "season_label",
                "round_label",
                "scoring_system",
                "points",
                "best_xi",
                "_events_dedupe_key",
            ],
            keep="last",
        ).drop(columns=["_events_dedupe_key"]).reset_index(drop=True)

    value_history_df = pd.DataFrame(value_history_rows)
    if value_history_df.empty:
        value_history_df = pd.DataFrame(columns=PLAYER_VALUE_COLUMNS)
    else:
        for column in PLAYER_VALUE_COLUMNS:
            if column not in value_history_df.columns:
                value_history_df[column] = None
        value_history_df = value_history_df[PLAYER_VALUE_COLUMNS].copy()
        value_history_df["date"] = pd.to_datetime(value_history_df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        value_history_df["market_value_eur"] = pd.to_numeric(value_history_df["market_value_eur"], errors="coerce")
        value_history_df = value_history_df.dropna(subset=["date", "market_value_eur"]).reset_index(drop=True)

    return stats_df, matches_df, value_history_df


def validate_player_payloads(
    stats_df: pd.DataFrame,
    matches_df: pd.DataFrame,
    value_history_df: pd.DataFrame,
) -> None:
    missing_stats = [column for column in PLAYER_STATS_COLUMNS if column not in stats_df.columns]
    missing_matches = [column for column in PLAYER_MATCHES_COLUMNS if column not in matches_df.columns]
    missing_values = [column for column in PLAYER_VALUE_COLUMNS if column not in value_history_df.columns]
    missing = {
        "stats": missing_stats,
        "matches": missing_matches,
        "values": missing_values,
    }
    missing = {name: columns for name, columns in missing.items() if columns}
    if missing:
        raise ValueError(f"Player payloads are missing columns: {missing}")

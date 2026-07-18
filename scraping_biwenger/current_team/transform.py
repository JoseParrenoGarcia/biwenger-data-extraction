import pandas as pd


CURRENT_TEAM_COLUMNS = [
    "name",
    "position_short",
    "position",
    "team_name",
    "player_slug",
    "player_url",
    "points",
    "previous_season_points",
    "market_value",
    "mv_change_eur",
    "status",
    "games_played",
    "average_points",
    "home_points",
    "home_average_points",
    "away_points",
    "away_average_points",
    "next_fixture_location",
    "next_opponent",
    "next_match_url",
    "next_match_id",
    "form_t-1",
    "form_t-2",
    "form_t-3",
    "form_t-4",
    "form_t-5",
]

INTEGER_COLUMNS = [
    "points",
    "market_value",
    "mv_change_eur",
    "games_played",
    "home_points",
    "away_points",
    "form_t-1",
    "form_t-2",
    "form_t-3",
    "form_t-4",
    "form_t-5",
]

FLOAT_COLUMNS = [
    "average_points",
    "home_average_points",
    "away_average_points",
]

NULLABLE_INTEGER_COLUMNS = [
    "previous_season_points",
    "next_match_id",
]

OPTIONAL_TEXT_COLUMNS = [
    "position_short",
    "position",
    "team_name",
    "player_slug",
    "player_url",
    "next_fixture_location",
    "next_opponent",
    "next_match_url",
]


def transform_current_team(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize scraped current-team rows into the Supabase table payload shape.
    """
    if raw_df is None or raw_df.empty:
        return pd.DataFrame(columns=CURRENT_TEAM_COLUMNS)

    missing = [column for column in CURRENT_TEAM_COLUMNS if column not in raw_df.columns]
    if missing:
        raise ValueError(f"Current-team scrape is missing columns: {missing}")

    df = raw_df[CURRENT_TEAM_COLUMNS].copy()
    df["name"] = df["name"].astype(str).str.strip()
    df["status"] = df["status"].astype(str).str.strip()

    for column in OPTIONAL_TEXT_COLUMNS:
        df[column] = df[column].map(
            lambda value: (
                stripped
                if (stripped := str(value).strip())
                else None
            )
            if pd.notna(value)
            else None
        )

    for column in INTEGER_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0).astype(int)

    for column in FLOAT_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0).astype(float)

    for column in NULLABLE_INTEGER_COLUMNS:
        values = pd.to_numeric(df[column], errors="coerce")
        df[column] = pd.Series(
            [int(value) if pd.notna(value) else None for value in values],
            index=df.index,
            dtype=object,
        )

    invalid_names = df["name"].eq("")
    if invalid_names.any():
        raise ValueError(f"Current-team payload contains {invalid_names.sum()} empty names.")

    return df


def validate_current_team_payload(df: pd.DataFrame) -> None:
    """
    Validate the dataframe immediately before persistence.
    """
    if df is None or df.empty:
        raise ValueError("Current-team payload is empty.")

    missing = [column for column in CURRENT_TEAM_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Current-team payload is missing columns: {missing}")

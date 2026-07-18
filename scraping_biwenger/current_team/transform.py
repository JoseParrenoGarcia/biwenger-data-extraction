import pandas as pd


CURRENT_TEAM_COLUMNS = [
    "name",
    "points",
    "market_value",
    "mv_change_eur",
    "status",
    "games_played",
    "average_points",
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
    "form_t-1",
    "form_t-2",
    "form_t-3",
    "form_t-4",
    "form_t-5",
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

    for column in INTEGER_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0).astype(int)

    df["average_points"] = (
        pd.to_numeric(df["average_points"], errors="coerce").fillna(0.0).astype(float)
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


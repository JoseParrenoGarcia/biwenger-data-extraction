import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd

from scraping_biwenger.players.transform import (
    PLAYER_MATCHES_COLUMNS,
    PLAYER_STATS_COLUMNS,
    PLAYER_VALUE_COLUMNS,
)

DEFAULT_CHECKPOINT_ROOT = "run_artifacts/player_runs"


def make_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid4().hex[:8]}"


def _json_default(value):
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _rows_from_df(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    clean = df.astype(object).where(df.notna(), None)
    return clean.to_dict(orient="records")


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=_json_default) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def dataframe_from_rows(rows: list[dict], columns: list[str]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=columns)
    df = pd.DataFrame(rows)
    for column in columns:
        if column not in df.columns:
            df[column] = None
    return df[columns]


@dataclass(frozen=True)
class PlayerCheckpointPayload:
    stats_df: pd.DataFrame
    matches_df: pd.DataFrame
    value_history_df: pd.DataFrame


class PlayerRunCheckpoint:
    def __init__(
        self,
        *,
        root_dir: str | Path = DEFAULT_CHECKPOINT_ROOT,
        run_id: str | None = None,
        metadata: dict | None = None,
    ):
        self.run_id = run_id or make_run_id()
        self.root_dir = Path(root_dir)
        self.run_dir = self.root_dir / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

        self.stats_path = self.run_dir / "player_stats.jsonl"
        self.matches_path = self.run_dir / "player_matches.jsonl"
        self.values_path = self.run_dir / "player_values.jsonl"
        self.errors_path = self.run_dir / "errors.jsonl"
        self.upload_errors_path = self.run_dir / "upload_errors.jsonl"
        self.metadata_path = self.run_dir / "metadata.json"
        self.run_log_path = self.run_dir / "run.log"

        self._ensure_files()
        if metadata is not None:
            self.write_metadata(metadata)

    def _ensure_files(self) -> None:
        for path in [
            self.stats_path,
            self.matches_path,
            self.values_path,
            self.errors_path,
            self.upload_errors_path,
        ]:
            path.touch(exist_ok=True)

    def write_metadata(self, metadata: dict) -> None:
        payload = {
            "run_id": self.run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            **metadata,
        }
        self.metadata_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default) + "\n",
            encoding="utf-8",
        )

    def append_payload(
        self,
        *,
        player: dict,
        stats_df: pd.DataFrame,
        matches_df: pd.DataFrame,
        value_history_df: pd.DataFrame,
    ) -> dict[str, int]:
        stats_rows = _rows_from_df(stats_df)
        match_rows = _rows_from_df(matches_df)
        value_rows = _rows_from_df(value_history_df)
        _append_jsonl(self.stats_path, stats_rows)
        _append_jsonl(self.matches_path, match_rows)
        _append_jsonl(self.values_path, value_rows)
        return {
            "stats": len(stats_rows),
            "matches": len(match_rows),
            "values": len(value_rows),
        }

    def append_player_error(self, *, player: dict, stage: str, message: str) -> None:
        _append_jsonl(
            self.errors_path,
            [
                {
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "stage": stage,
                    "player": player,
                    "message": message,
                }
            ],
        )

    def append_upload_error(
        self,
        *,
        batch_number: int,
        stats_rows: int,
        match_rows: int,
        value_rows: int,
        message: str,
    ) -> None:
        _append_jsonl(
            self.upload_errors_path,
            [
                {
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "batch_number": batch_number,
                    "stats_rows": stats_rows,
                    "match_rows": match_rows,
                    "value_rows": value_rows,
                    "message": message,
                }
            ],
        )


def read_player_checkpoint(run_dir: str | Path) -> PlayerCheckpointPayload:
    run_path = Path(run_dir)
    stats_rows = _read_jsonl(run_path / "player_stats.jsonl")
    match_rows = _read_jsonl(run_path / "player_matches.jsonl")
    value_rows = _read_jsonl(run_path / "player_values.jsonl")
    return PlayerCheckpointPayload(
        stats_df=dataframe_from_rows(stats_rows, PLAYER_STATS_COLUMNS),
        matches_df=dataframe_from_rows(match_rows, PLAYER_MATCHES_COLUMNS),
        value_history_df=dataframe_from_rows(value_rows, PLAYER_VALUE_COLUMNS),
    )


def cleanup_old_player_runs(
    root_dir: str | Path = DEFAULT_CHECKPOINT_ROOT,
    *,
    retention_days: int = 7,
    now: datetime | None = None,
) -> list[Path]:
    """
    Delete checkpoint run directories older than retention_days.

    Only direct child directories of root_dir are considered. Files are ignored.
    """
    root_path = Path(root_dir)
    if retention_days < 0 or not root_path.exists():
        return []

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=retention_days)
    deleted: list[Path] = []

    for run_path in root_path.iterdir():
        if not run_path.is_dir():
            continue
        modified_at = datetime.fromtimestamp(run_path.stat().st_mtime, timezone.utc)
        if modified_at >= cutoff:
            continue
        shutil.rmtree(run_path)
        deleted.append(run_path)

    return deleted

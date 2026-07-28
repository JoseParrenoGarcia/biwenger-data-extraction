from __future__ import annotations

from dataclasses import dataclass, field

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from scraping_biwenger.players.run_events import PlayerRunEvent


@dataclass
class RecentOutcome:
    label: str
    status: str
    scoring_system: str = "n/a"
    stats_rows: int = 0
    match_rows: int = 0
    value_rows: int = 0
    stage: str = ""
    note: str = ""


@dataclass
class PlayerRunTerminalState:
    run_id: str = ""
    run_dir: str = ""
    mode_summary: str = ""
    processed_players: int = 0
    total_players: int = 0
    current_player: str = ""
    current_player_rank: int = 0
    current_player_team: str = ""
    current_player_attempt: str = "initial"
    recent_outcomes: list[RecentOutcome] = field(default_factory=list)
    pending_stats_rows: int = 0
    pending_match_rows: int = 0
    pending_value_rows: int = 0
    batch_number: int = 0
    upload_failure_count: int = 0
    warning_count: int = 0
    notices: list[str] = field(default_factory=list)
    retry_queue_count: int = 0
    retry_active: bool = False
    retry_recovered: int = 0
    retry_failed: int = 0
    termination_reason: str = ""
    final_summary: str = ""

    def append_notice(self, message: str) -> None:
        if not message:
            return
        self.notices.append(message)
        self.notices = self.notices[-6:]

    def append_outcome(self, outcome: RecentOutcome) -> None:
        self.recent_outcomes.append(outcome)
        self.recent_outcomes = self.recent_outcomes[-8:]

    def apply_event(self, event: PlayerRunEvent) -> None:
        event_type = event["type"]
        if event_type == "run_started":
            self.run_id = event.get("run_id", "")
            self.run_dir = event.get("run_dir", "")
            mode_bits = [
                "dry-run" if event.get("dry_run") else "write",
                "headed" if event.get("headed") else "headless",
                f"max-players={event.get('max_players_detail')}",
                f"retry-top={event.get('retry_top_players')}",
                f"batch={event.get('upload_batch_size')}",
            ]
            self.mode_summary = " | ".join(mode_bits)
        elif event_type == "player_started":
            self.current_player = event.get("player_name") or event.get("player_slug") or ""
            self.current_player_rank = event.get("rank") or 0
            self.current_player_team = event.get("team") or ""
            self.current_player_attempt = event.get("attempt_label") or "initial"
            self.total_players = max(self.total_players, event.get("total_players") or 0)
        elif event_type == "checkpoint_written":
            self.pending_stats_rows += event.get("stats_rows", 0)
            self.pending_match_rows += event.get("match_rows", 0)
            self.pending_value_rows += event.get("value_rows", 0)
            self.append_notice(
                "Checkpointed "
                f"{event.get('player_slug') or event.get('player_name', '')} "
                f"(s={event.get('stats_rows', 0)} m={event.get('match_rows', 0)} v={event.get('value_rows', 0)})"
            )
        elif event_type == "player_finished":
            self.processed_players = max(self.processed_players, event.get("processed_count") or 0)
            self.current_player = ""
            self.current_player_rank = 0
            self.current_player_team = ""
            stage = event.get("stage", "")
            self.append_outcome(
                RecentOutcome(
                    label=event.get("player_slug") or event.get("player_name") or "",
                    status="warning" if stage and stage != "ok" else "ok",
                    scoring_system=event.get("scoring_system", "n/a"),
                    stats_rows=event.get("stats_rows", 0),
                    match_rows=event.get("match_rows", 0),
                    value_rows=event.get("value_rows", 0),
                    stage=stage,
                    note=event.get("note", ""),
                )
            )
        elif event_type == "player_failed":
            self.warning_count += 1
            self.current_player = ""
            self.current_player_rank = 0
            self.current_player_team = ""
            self.append_outcome(
                RecentOutcome(
                    label=event.get("player_slug") or event.get("player_name") or "",
                    status="failed",
                    stage=event.get("stage", ""),
                    note=(event.get("message", "") or "")[:80],
                )
            )
        elif event_type == "player_value_incomplete":
            self.warning_count += 1
            self.append_notice(
                "Value history incomplete for "
                f"{event.get('player_slug') or event.get('player_name', '')} "
                f"(reason={event.get('reason', '')} m={event.get('match_rows', 0)} v={event.get('value_rows', 0)})"
            )
        elif event_type == "batch_upload_started":
            self.batch_number = event.get("batch_number", self.batch_number)
            self.append_notice(
                f"Uploading batch {self.batch_number} "
                f"(s={event.get('stats_rows', 0)} m={event.get('match_rows', 0)} v={event.get('value_rows', 0)})"
            )
        elif event_type == "batch_upload_finished":
            self.batch_number = event.get("batch_number", self.batch_number)
            self.pending_stats_rows = 0
            self.pending_match_rows = 0
            self.pending_value_rows = 0
            self.append_notice(f"Batch {self.batch_number} uploaded successfully")
        elif event_type == "batch_upload_failed":
            self.batch_number = event.get("batch_number", self.batch_number)
            self.upload_failure_count += 1
            self.warning_count += 1
            self.append_notice(f"Batch {self.batch_number} upload failed; checkpoint kept locally")
        elif event_type == "retry_queued":
            self.retry_queue_count += 1
            self.append_notice(
                f"Retry queued for {event.get('player_slug') or event.get('player_name', '')} "
                f"(rank={event.get('rank')} stage={event.get('stage')})"
            )
        elif event_type == "player_value_retry_queued":
            self.retry_queue_count += 1
            self.append_notice(
                "Value retry queued for "
                f"{event.get('player_slug') or event.get('player_name', '')} "
                f"(rank={event.get('rank')} reason={event.get('reason', '')})"
            )
        elif event_type == "retry_pass_started":
            self.retry_active = True
            self.append_notice(f"Retry pass started for {event.get('retry_count', 0)} players")
        elif event_type == "retry_pass_finished":
            self.retry_active = False
            self.retry_recovered = event.get("recovered_count", 0)
            self.retry_failed = event.get("failed_count", 0)
            self.append_notice(f"Retry pass finished: recovered={self.retry_recovered} failed={self.retry_failed}")
        elif event_type == "value_retry_pass_started":
            self.retry_active = True
            self.append_notice(f"Value retry pass started for {event.get('retry_count', 0)} players")
        elif event_type == "value_retry_pass_finished":
            self.retry_active = False
            self.retry_recovered = event.get("recovered_count", 0)
            self.retry_failed = event.get("failed_count", 0)
            self.append_notice(
                f"Value retry pass finished: recovered={self.retry_recovered} failed={self.retry_failed}"
            )
        elif event_type == "circuit_breaker_triggered":
            self.warning_count += 1
            self.termination_reason = "circuit_breaker"
            self.append_notice(
                "Circuit breaker triggered for "
                f"{event.get('player_slug') or event.get('player_name', '')} "
                f"(rank={event.get('rank')} stage={event.get('stage')})"
            )
        elif event_type == "run_finished":
            self.termination_reason = event.get("termination_reason", self.termination_reason)
            self.final_summary = event.get("summary", "")


def _status_text(status: str) -> Text:
    if status == "ok":
        return Text("ok", style="bold green")
    if status == "warning":
        return Text("warning", style="bold yellow")
    if status == "failed":
        return Text("failed", style="bold red")
    return Text(status or "n/a")


def build_terminal_ui_renderable(state: PlayerRunTerminalState):
    header = Table.grid(expand=True)
    header.add_column(ratio=3)
    header.add_column(ratio=2)
    header.add_row(
        f"[bold]Player Scrape Run[/bold]\n{state.run_id}\n{state.mode_summary}",
        f"[bold]Checkpoint[/bold]\n{state.run_dir}",
    )

    progress = Table.grid(expand=True)
    progress.add_column(ratio=1)
    progress.add_column(ratio=1)
    progress.add_row(
        f"[bold]Progress[/bold]\n{state.processed_players}/{state.total_players or '?'} players",
        (
            "[bold]Current[/bold]\n"
            f"{state.current_player or '-'} "
            f"{f'(#{state.current_player_rank})' if state.current_player_rank else ''}\n"
            f"{state.current_player_team or state.current_player_attempt}"
        ),
    )

    upload = Table.grid(expand=True)
    upload.add_column(ratio=1)
    upload.add_column(ratio=1)
    upload.add_row(
        (
            "[bold]Pending buffer[/bold]\n"
            f"stats={state.pending_stats_rows} "
            f"matches={state.pending_match_rows} "
            f"values={state.pending_value_rows}"
        ),
        (f"[bold]Uploads[/bold]\nlast_batch={state.batch_number} failures={state.upload_failure_count}"),
    )

    outcomes = Table(expand=True, box=None)
    outcomes.add_column("Player")
    outcomes.add_column("Status")
    outcomes.add_column("Scoring")
    outcomes.add_column("Rows")
    outcomes.add_column("Note")
    for outcome in state.recent_outcomes[-6:]:
        outcomes.add_row(
            outcome.label,
            _status_text(outcome.status),
            outcome.scoring_system,
            f"{outcome.stats_rows}/{outcome.match_rows}/{outcome.value_rows}",
            outcome.note or outcome.stage,
        )
    if not state.recent_outcomes:
        outcomes.add_row("-", "-", "-", "-", "-")

    notices = Table(expand=True, box=None)
    notices.add_column("Recent status")
    for note in state.notices[-5:]:
        notices.add_row(note)
    if not state.notices:
        notices.add_row("No notable events yet")

    footer_text = state.final_summary or (
        f"warnings={state.warning_count} retries={state.retry_queue_count} "
        f"retry_active={'yes' if state.retry_active else 'no'} "
        f"termination={state.termination_reason or 'running'}"
    )

    return Group(
        Panel(header, title="Run"),
        Panel(progress, title="Progress"),
        Panel(upload, title="Uploads"),
        Panel(outcomes, title="Recent outcomes"),
        Panel(notices, title="Status"),
        Panel(footer_text, title="Summary"),
    )


class PlayerRunTerminalUI:
    def __init__(self) -> None:
        self.state = PlayerRunTerminalState()
        self.console = Console(stderr=True)
        self.live = Live(
            build_terminal_ui_renderable(self.state),
            console=self.console,
            refresh_per_second=4,
            transient=False,
            auto_refresh=False,
        )
        self._started = False

    def start(self) -> None:
        if not self._started:
            self.live.start()
            self._started = True

    def handle_event(self, event: PlayerRunEvent) -> None:
        if not self._started:
            self.start()
        self.state.apply_event(event)
        self.live.update(build_terminal_ui_renderable(self.state), refresh=True)

    def close(self) -> None:
        if self._started:
            self.live.update(build_terminal_ui_renderable(self.state), refresh=True)
            self.live.stop()
            self._started = False


def build_run_players_ui_command(python_path: str = ".venv/bin/python") -> str:
    return (
        f"{python_path} -m scraping_biwenger.get_player_stats "
        "--headed --dry-run --terminal-ui --max-player-pages 1 --max-players 2"
    )

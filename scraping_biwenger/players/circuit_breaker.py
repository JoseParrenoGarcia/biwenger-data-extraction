from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

BREAKER_RELEVANT_STAGES = {
    "open_player",
    "select_scoring_system",
    "scrape_detail",
}


@dataclass
class PlayerRunCircuitBreaker:
    consecutive_failures_threshold: int = 4
    window_size: int = 10
    window_failures_threshold: int = 8
    consecutive_failures: int = 0
    recent_failures: deque[bool] = field(default_factory=deque)
    triggered: bool = False
    trigger_stage: str = ""
    trigger_message: str = ""
    trigger_player_slug: str = ""
    trigger_rank: int | None = None

    def record_success(self) -> None:
        if self.triggered:
            return
        self.consecutive_failures = 0
        self._append_recent(False)

    def record_failure(self, *, stage: str, message: str, player_slug: str = "", rank: int | None = None) -> bool:
        if stage not in BREAKER_RELEVANT_STAGES:
            return False
        if self.triggered:
            return True
        self.consecutive_failures += 1
        self._append_recent(True)
        if self._should_trigger():
            self.triggered = True
            self.trigger_stage = stage
            self.trigger_message = message
            self.trigger_player_slug = player_slug
            self.trigger_rank = rank
        return self.triggered

    @property
    def recent_failure_count(self) -> int:
        return sum(1 for failed in self.recent_failures if failed)

    def state_payload(self) -> dict:
        return {
            "circuit_breaker_triggered": self.triggered,
            "circuit_breaker_stage": self.trigger_stage,
            "circuit_breaker_message": self.trigger_message,
            "circuit_breaker_player_slug": self.trigger_player_slug,
            "circuit_breaker_rank": self.trigger_rank,
            "circuit_breaker_consecutive_failures": self.consecutive_failures,
            "circuit_breaker_recent_failure_count": self.recent_failure_count,
            "circuit_breaker_window_size": self.window_size,
            "circuit_breaker_window_failures": self.window_failures_threshold,
        }

    def _append_recent(self, failed: bool) -> None:
        self.recent_failures.append(failed)
        while len(self.recent_failures) > self.window_size:
            self.recent_failures.popleft()

    def _should_trigger(self) -> bool:
        return self.consecutive_failures >= self.consecutive_failures_threshold or (
            len(self.recent_failures) >= self.window_size
            and self.recent_failure_count >= self.window_failures_threshold
        )

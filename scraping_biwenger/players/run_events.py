from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

PlayerRunEvent = dict[str, Any]
PlayerRunEventHandler = Callable[[PlayerRunEvent], None]


def _event_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_player_run_event(event_type: str, **payload: Any) -> PlayerRunEvent:
    return {
        "type": event_type,
        "recorded_at": _event_timestamp(),
        **payload,
    }


@dataclass
class PlayerRunEventEmitter:
    subscribers: list[PlayerRunEventHandler]

    def emit(self, event_type: str, **payload: Any) -> PlayerRunEvent:
        event = make_player_run_event(event_type, **payload)
        for subscriber in self.subscribers:
            subscriber(event)
        return event


def build_event_emitter(*subscribers: PlayerRunEventHandler | None) -> PlayerRunEventEmitter:
    return PlayerRunEventEmitter([subscriber for subscriber in subscribers if subscriber is not None])

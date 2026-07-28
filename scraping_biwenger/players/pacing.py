from __future__ import annotations

from dataclasses import dataclass
from random import uniform
from time import sleep


@dataclass(frozen=True)
class PlayerRunPacingPolicy:
    profile: str
    enabled: bool = True

    def apply(self, point: str, *, processed: int = 0) -> None:
        if not self.enabled or self.profile == "off":
            return

        delay = _delay_for_point(self.profile, point, processed=processed)
        if delay <= 0:
            return
        sleep(delay)


def build_pacing_policy(profile: str, *, targeted_player: bool = False) -> PlayerRunPacingPolicy:
    normalized = (profile or "normal").strip().lower()
    if normalized not in {"off", "normal", "slow"}:
        raise ValueError(f"Unsupported pacing profile '{profile}'. Expected one of: off, normal, slow.")
    if targeted_player:
        return PlayerRunPacingPolicy(profile="off", enabled=False)
    return PlayerRunPacingPolicy(profile=normalized, enabled=normalized != "off")


def _delay_for_point(profile: str, point: str, *, processed: int = 0) -> float:
    if point == "after_open":
        return _sample(profile, 0.8, 1.8, slow=(1.5, 3.0))
    if point == "before_scoring":
        return _sample(profile, 0.6, 1.5, slow=(1.2, 2.5))
    if point == "before_value":
        return _sample(profile, 0.5, 1.2, slow=(1.0, 2.0))
    if point == "after_player":
        return _sample(profile, 0.8, 2.5, slow=(1.5, 4.0))
    if point == "every_10_players" and processed > 0 and processed % 10 == 0:
        return _sample(profile, 5.0, 12.0, slow=(8.0, 18.0))
    if point == "every_50_players" and processed > 0 and processed % 50 == 0:
        return _sample(profile, 20.0, 45.0, slow=(30.0, 60.0))
    return 0.0


def _sample(profile: str, start: float, end: float, *, slow: tuple[float, float]) -> float:
    if profile == "slow":
        return uniform(*slow)
    return uniform(start, end)

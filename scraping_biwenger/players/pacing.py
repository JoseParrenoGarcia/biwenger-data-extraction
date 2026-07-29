from __future__ import annotations

from dataclasses import dataclass
from random import uniform
from time import sleep
from typing import Any


@dataclass(frozen=True)
class PlayerRunPacingPolicy:
    profile: str
    enabled: bool = True
    logger: Any | None = None

    def apply(self, point: str, *, processed: int = 0) -> None:
        if not self.enabled or self.profile == "off":
            return

        delay = _delay_for_point(self.profile, point, processed=processed)
        if delay <= 0:
            return
        if self.logger:
            self.logger.debug(
                "PACING point=%s profile=%s processed=%s delay_s=%.2f",
                point,
                self.profile,
                processed,
                delay,
            )
        sleep(delay)


def build_pacing_policy(profile: str, *, targeted_player: bool = False, logger=None) -> PlayerRunPacingPolicy:
    normalized = (profile or "human").strip().lower()
    if normalized not in {"off", "normal", "human", "slow"}:
        raise ValueError(f"Unsupported pacing profile '{profile}'. Expected one of: off, normal, human, slow.")
    if targeted_player:
        return PlayerRunPacingPolicy(profile="off", enabled=False, logger=logger)
    return PlayerRunPacingPolicy(profile=normalized, enabled=normalized != "off", logger=logger)


def _delay_for_point(profile: str, point: str, *, processed: int = 0) -> float:
    if point == "after_open":
        return _sample(profile, normal=(0.8, 1.8), human=(1.8, 4.0), slow=(3.0, 6.0))
    if point == "before_scoring":
        return _sample(profile, normal=(0.6, 1.5), human=(1.2, 3.0), slow=(2.0, 4.5))
    if point == "before_value":
        return _sample(profile, normal=(0.5, 1.2), human=(1.0, 2.5), slow=(1.8, 4.0))
    if point == "after_player":
        return _sample(profile, normal=(0.8, 2.5), human=(2.0, 5.0), slow=(3.0, 7.0))
    if point == "before_paginate":
        return _sample(profile, normal=(0.35, 0.9), human=(0.8, 2.0), slow=(1.5, 3.5))
    if point == "after_paginate":
        return _sample(profile, normal=(0.5, 1.1), human=(0.8, 1.8), slow=(1.2, 2.6))
    if point == "every_10_players" and processed > 0 and processed % 10 == 0:
        return _sample(profile, normal=(5.0, 12.0), human=(12.0, 28.0), slow=(20.0, 40.0))
    if point == "every_50_players" and processed > 0 and processed % 50 == 0:
        return _sample(profile, normal=(20.0, 45.0), human=(60.0, 120.0), slow=(90.0, 180.0))
    return 0.0


def _sample(
    profile: str,
    *,
    normal: tuple[float, float],
    human: tuple[float, float],
    slow: tuple[float, float],
) -> float:
    if profile == "slow":
        return uniform(*slow)
    if profile == "human":
        return uniform(*human)
    return uniform(*normal)

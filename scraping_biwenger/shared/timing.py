import time
import random
import re


def _timing_stage(label: str) -> str:
    stage = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return stage or "unknown"


def _log_timing(logger, message: str, started_at: float) -> None:
    if logger:
        logger.info("%s in %.2fs", message, time.perf_counter() - started_at)


def log_timing_debug(logger, label: str, started_at: float, *, player_slug: str = "") -> None:
    if logger:
        logger.debug(
            "TIMING stage=%s player_slug=%s duration_s=%.2f",
            _timing_stage(label),
            player_slug or "",
            time.time() - started_at,
        )


def _rand_sleep(a: float = 0.25, b: float = 1.5) -> None:
    time.sleep(random.uniform(a, b))

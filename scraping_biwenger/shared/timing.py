import time
import random


def _log_timing(logger, message: str, started_at: float) -> None:
    if logger:
        logger.info("%s in %.2fs", message, time.perf_counter() - started_at)


def _rand_sleep(a: float = 0.25, b: float = 1.5) -> None:
    time.sleep(random.uniform(a, b))

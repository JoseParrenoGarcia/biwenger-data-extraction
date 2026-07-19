import time


def _log_timing(logger, message: str, started_at: float) -> None:
    if logger:
        logger.info("%s in %.2fs", message, time.perf_counter() - started_at)

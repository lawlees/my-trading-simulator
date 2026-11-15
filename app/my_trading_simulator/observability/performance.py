
"""Structured performance logging for my-trading-simulator.

Records operation duration using a monotonic clock.
Never logs OAuth tokens, API keys, or Discord message text.
"""

import json
import os
import sys
from functools import wraps
import logging
import re
import time
from contextlib import contextmanager

logger = logging.getLogger("my_trading_simulator.performance")

_ALLOWED_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@contextmanager
def measure(operation: str):
    """Measure an operation and log duration in milliseconds."""
    if not _ALLOWED_NAME.fullmatch(operation):
        raise ValueError("Invalid performance operation name")

    _enable_worker_logging_if_requested()
    start = time.perf_counter()
    status = "success"

    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        elapsed_ms = round(
            (time.perf_counter() - start) * 1000,
            2,
        )

        logger.info(
            json.dumps({
                "event": "performance",
                "operation": operation,
                "duration_ms": elapsed_ms,
                "status": status,
            })
        )


def _enable_worker_logging_if_requested() -> None:
    """Opt-in JSONL stderr logging for systemd/journald; no secrets or inputs."""
    if os.getenv("MY_TRADING_SIMULATOR_PERFORMANCE_LOGGING") != "1":
        return
    if not any(getattr(handler, "_mts_performance", False) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler._mts_performance = True
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def timed(operation: str):
    """Decorator: time a callable without logging parameters or return values."""
    if not _ALLOWED_NAME.fullmatch(operation):
        raise ValueError("Invalid performance operation name")

    def decorate(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            with measure(operation):
                return func(*args, **kwargs)
        return wrapped
    return decorate

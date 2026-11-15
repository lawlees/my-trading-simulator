
"""Dedicated read-only Schwab market-data worker.

Safety rules:
- Runs separately from FastAPI and Discord ingestion.
- Acquires an exclusive lock before Schwab client initialization.
- Holds the lock for the entire operation.
- Does not initialize Schwab during module import.
- Does not submit brokerage orders.
- Actual Schwab API operations remain disabled in the CLI.
"""

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from my_trading_simulator.observability.performance import timed
from my_trading_simulator.market_data.schwab_worker_lock import (
    SchwabWorkerLock,
)


DEFAULT_LOCK_PATH = Path(
    "/var/lib/schwab-worker/schwab-oauth.lock"
)

T = TypeVar("T")


def run_with_exclusive_lock(
    operation: Callable[[], T],
    *,
    lock_path: str | Path = DEFAULT_LOCK_PATH,
) -> T:
    """Run an operation while holding the exclusive worker lock.

    The lock is acquired before the operation starts and remains
    held until it completes or raises an exception.
    """
    with SchwabWorkerLock(lock_path):
        return operation()


@timed("schwab_locked_operation")
def run_schwab_operation(
    operation: Callable,
    *,
    client_factory=None,
    lock_path: str | Path = DEFAULT_LOCK_PATH,
):
    """Initialize Schwab and execute one operation under the lock.

    The client is created only after acquiring the lock.

    All OAuth reads, refreshes, token writes and market-data
    requests must remain inside the locked operation.

    This function does not authorize brokerage order placement.
    """
    if client_factory is None:
        from my_trading_simulator.market_data.schwab_client import (
            SchwabMarketDataClient,
        )

        client_factory = SchwabMarketDataClient

    def locked_operation():
        client = client_factory()
        return operation(client)

    return run_with_exclusive_lock(
        locked_operation,
        lock_path=lock_path,
    )


def check_worker_lock(
    *,
    lock_path: str | Path = DEFAULT_LOCK_PATH,
) -> None:
    """Test lock acquisition without initializing Schwab."""
    run_with_exclusive_lock(
        lambda: None,
        lock_path=lock_path,
    )


def check_worker_startup(
    *,
    lock_path: str | Path = DEFAULT_LOCK_PATH,
) -> None:
    """Test locked client initialization using a fake client.

    Makes no AWS or Schwab API requests.
    """

    class FakeSchwabClient:
        def __init__(self):
            self.ready = True

    def verify_client(client):
        if not isinstance(client, FakeSchwabClient):
            raise RuntimeError(
                "Unexpected worker startup client"
            )

        if not client.ready:
            raise RuntimeError(
                "Worker startup validation failed"
            )

    run_schwab_operation(
        verify_client,
        client_factory=FakeSchwabClient,
        lock_path=lock_path,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Schwab market-data worker"
    )

    commands = parser.add_mutually_exclusive_group(
        required=True
    )

    commands.add_argument(
        "--check-lock",
        action="store_true",
        help="Check worker locking without Schwab access",
    )

    commands.add_argument(
        "--check-startup",
        action="store_true",
        help="Check locked startup with a fake Schwab client",
    )

    args = parser.parse_args(argv)

    if args.check_lock:
        check_worker_lock()

        print("Schwab worker lock check: PASSED")
        print("Schwab API requests: DISABLED")
        print("Live trading: DISABLED")
        return 0

    if args.check_startup:
        check_worker_startup()

        print("Schwab worker startup check: PASSED")
        print("Exclusive lock: VERIFIED")
        print("Schwab API requests: DISABLED")
        print("Live trading: DISABLED")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

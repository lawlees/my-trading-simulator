"""Verify canonical Schwab worker lock configuration."""

from pathlib import Path

from my_trading_simulator.market_data import (
    schwab_market_data_worker as worker,
)


EXPECTED_LOCK_PATH = Path(
    "/var/lib/schwab-worker/schwab-market-data.lock"
)


def test_default_lock_path_is_canonical():
    assert worker.DEFAULT_LOCK_PATH == EXPECTED_LOCK_PATH


def test_lock_helpers_use_canonical_default(monkeypatch):
    """Verify both helpers use the same lock path."""

    observed_paths = []

    class RecordingLock:
        def __init__(self, lock_path):
            observed_paths.append(Path(lock_path))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        worker,
        "SchwabWorkerLock",
        RecordingLock,
    )

    worker.run_with_exclusive_lock(lambda: None)

    result = worker.run_schwab_operation(
        lambda client: client,
        client_factory=lambda: "FAKE_CLIENT",
    )

    assert result == "FAKE_CLIENT"
    assert observed_paths == [
        EXPECTED_LOCK_PATH,
        EXPECTED_LOCK_PATH,
    ]

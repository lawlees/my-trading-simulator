
"""Test local Schwab OAuth storage under the exclusive worker lock."""

import pytest

from my_trading_simulator.market_data.schwab_local_token_store import (
    SchwabLocalTokenStore,
)
from my_trading_simulator.market_data.schwab_market_data_worker import (
    run_with_exclusive_lock,
)
from my_trading_simulator.market_data.schwab_worker_lock import (
    SchwabWorkerLock,
)


def test_token_read_write_inside_worker_lock(tmp_path):
    lock_path = tmp_path / "schwab.lock"
    token_path = tmp_path / "schwab_token.json"

    store = SchwabLocalTokenStore(token_path)

    fake_token = {
        "creation_timestamp": 1700000000,
        "token": {
            "access_token": "fake-access-token",
            "refresh_token": "fake-refresh-token",
        },
    }

    def operation():
        store.write_token(fake_token)

        assert store.read_token() == fake_token

        # A competing worker must not acquire the same lock.
        with pytest.raises(
            RuntimeError,
            match="Another Schwab worker is already running",
        ):
            with SchwabWorkerLock(lock_path):
                pass

        return "SUCCESS"

    result = run_with_exclusive_lock(
        operation,
        lock_path=lock_path,
    )

    assert result == "SUCCESS"

    # After the worker exits, the lock is available again.
    with SchwabWorkerLock(lock_path):
        pass


def test_failed_token_write_releases_worker_lock(tmp_path):
    lock_path = tmp_path / "schwab.lock"
    token_path = tmp_path / "schwab_token.json"

    store = SchwabLocalTokenStore(token_path)

    def operation():
        store.write_token({"token": {}})

    with pytest.raises(ValueError):
        run_with_exclusive_lock(
            operation,
            lock_path=lock_path,
        )

    with SchwabWorkerLock(lock_path):
        pass

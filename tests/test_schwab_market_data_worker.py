
"""Tests for Schwab market-data worker lock integration."""

import pytest

from my_trading_simulator.market_data.schwab_market_data_worker import (
    run_with_exclusive_lock,
)
from my_trading_simulator.market_data.schwab_worker_lock import (
    SchwabWorkerLock,
)


def test_operation_runs_while_lock_is_held(tmp_path):
    lock_path = tmp_path / "schwab.lock"
    executed = []

    def operation():
        executed.append("started")

        with pytest.raises(
            RuntimeError,
            match="Another Schwab worker is already running",
        ):
            with SchwabWorkerLock(lock_path):
                pass

        executed.append("finished")
        return "SUCCESS"

    result = run_with_exclusive_lock(
        operation,
        lock_path=lock_path,
    )

    assert result == "SUCCESS"
    assert executed == ["started", "finished"]


def test_lock_released_after_success(tmp_path):
    lock_path = tmp_path / "schwab.lock"

    run_with_exclusive_lock(
        lambda: "SUCCESS",
        lock_path=lock_path,
    )

    with SchwabWorkerLock(lock_path):
        pass


def test_lock_released_after_failure(tmp_path):
    lock_path = tmp_path / "schwab.lock"

    def failing_operation():
        raise ValueError("Simulated worker failure")

    with pytest.raises(
        ValueError,
        match="Simulated worker failure",
    ):
        run_with_exclusive_lock(
            failing_operation,
            lock_path=lock_path,
        )

    with SchwabWorkerLock(lock_path):
        pass


def test_second_worker_operation_is_rejected(tmp_path):
    lock_path = tmp_path / "schwab.lock"

    def competing_operation():
        return run_with_exclusive_lock(
            lambda: "SECOND_WORKER_STARTED",
            lock_path=lock_path,
        )

    with pytest.raises(
        RuntimeError,
        match="Another Schwab worker is already running",
    ):
        run_with_exclusive_lock(
            competing_operation,
            lock_path=lock_path,
        )


def test_schwab_client_initialized_under_lock(tmp_path):
    """Client initialization and operation must both hold the lock."""
    from my_trading_simulator.market_data.schwab_market_data_worker import (
        run_schwab_operation,
    )

    lock_path = tmp_path / "schwab.lock"
    events = []

    def assert_lock_held():
        with pytest.raises(
            RuntimeError,
            match="Another Schwab worker is already running",
        ):
            with SchwabWorkerLock(lock_path):
                pass

    class FakeSchwabClient:
        def __init__(self):
            assert_lock_held()
            events.append("client_initialized")

    def operation(client):
        assert_lock_held()
        assert isinstance(client, FakeSchwabClient)
        events.append("operation_completed")
        return "SUCCESS"

    result = run_schwab_operation(
        operation,
        client_factory=FakeSchwabClient,
        lock_path=lock_path,
    )

    assert result == "SUCCESS"
    assert events == [
        "client_initialized",
        "operation_completed",
    ]


def test_lock_released_after_client_initialization_failure(tmp_path):
    """A failed Schwab authentication must release the lock."""
    from my_trading_simulator.market_data.schwab_market_data_worker import (
        run_schwab_operation,
    )

    lock_path = tmp_path / "schwab.lock"

    class FailingSchwabClient:
        def __init__(self):
            raise RuntimeError("Simulated Schwab authentication failure")

    with pytest.raises(
        RuntimeError,
        match="Simulated Schwab authentication failure",
    ):
        run_schwab_operation(
            lambda client: None,
            client_factory=FailingSchwabClient,
            lock_path=lock_path,
        )

    # A future worker should be able to acquire the lock.
    with SchwabWorkerLock(lock_path):
        pass


def test_lock_released_after_schwab_operation_failure(tmp_path):
    """A failed market-data operation must release the lock."""
    from my_trading_simulator.market_data.schwab_market_data_worker import (
        run_schwab_operation,
    )

    lock_path = tmp_path / "schwab.lock"

    class FakeSchwabClient:
        pass

    def failing_operation(client):
        raise RuntimeError("Simulated market-data failure")

    with pytest.raises(
        RuntimeError,
        match="Simulated market-data failure",
    ):
        run_schwab_operation(
            failing_operation,
            client_factory=FakeSchwabClient,
            lock_path=lock_path,
        )

    with SchwabWorkerLock(lock_path):
        pass

def test_startup_check_succeeds(tmp_path):
    from my_trading_simulator.market_data.schwab_market_data_worker import (
        check_worker_startup,
    )

    check_worker_startup(
        lock_path=tmp_path / "schwab.lock"
    )


def test_startup_check_rejects_competing_worker(tmp_path):
    from my_trading_simulator.market_data.schwab_market_data_worker import (
        check_worker_startup,
    )

    lock_path = tmp_path / "schwab.lock"

    with SchwabWorkerLock(lock_path):
        with pytest.raises(
            RuntimeError,
            match="Another Schwab worker is already running",
        ):
            check_worker_startup(lock_path=lock_path)


def test_startup_check_releases_lock(tmp_path):
    from my_trading_simulator.market_data.schwab_market_data_worker import (
        check_worker_startup,
    )

    lock_path = tmp_path / "schwab.lock"

    check_worker_startup(lock_path=lock_path)

    # Lock must be available after startup check finishes.
    with SchwabWorkerLock(lock_path):
        pass

def test_cli_rejects_missing_command():
    """Worker must not run Schwab by default."""
    from my_trading_simulator.market_data.schwab_market_data_worker import (
        main,
    )

    with pytest.raises(SystemExit) as error:
        main([])

    assert error.value.code == 2


def test_cli_rejects_unrecognized_market_data_command():
    """Real Schwab access must remain disabled."""
    from my_trading_simulator.market_data.schwab_market_data_worker import (
        main,
    )

    with pytest.raises(SystemExit) as error:
        main(["--run-market-data"])

    assert error.value.code == 2

"""Tests for exclusive Schwab worker locking."""

import multiprocessing
from pathlib import Path

import pytest

from my_trading_simulator.market_data.schwab_worker_lock import (
    SchwabWorkerLock,
)


def test_lock_can_be_acquired_and_released(tmp_path):
    lock_path = tmp_path / "schwab.lock"

    with SchwabWorkerLock(lock_path):
        assert lock_path.exists()

    # Lock must be reusable after release.
    with SchwabWorkerLock(lock_path):
        pass


def test_second_lock_is_rejected(tmp_path):
    lock_path = tmp_path / "schwab.lock"

    with SchwabWorkerLock(lock_path):
        with pytest.raises(
            RuntimeError,
            match="Another Schwab worker is already running",
        ):
            with SchwabWorkerLock(lock_path):
                pass


def test_lock_released_after_exception(tmp_path):
    lock_path = tmp_path / "schwab.lock"

    with pytest.raises(ValueError):
        with SchwabWorkerLock(lock_path):
            raise ValueError("Simulated worker failure")

    # Exception must not leave the lock held.
    with SchwabWorkerLock(lock_path):
        pass


def test_same_instance_cannot_acquire_twice(tmp_path):
    lock = SchwabWorkerLock(tmp_path / "schwab.lock")

    try:
        lock.acquire()

        with pytest.raises(
            RuntimeError,
            match="Schwab worker lock already acquired",
        ):
            lock.acquire()
    finally:
        lock.release()


def test_release_without_acquire_is_safe(tmp_path):
    lock = SchwabWorkerLock(tmp_path / "schwab.lock")

    lock.release()
    lock.release()


def test_lock_released_explicitly(tmp_path):
    lock_path = tmp_path / "schwab.lock"

    lock = SchwabWorkerLock(lock_path)
    lock.acquire()
    lock.release()

    with SchwabWorkerLock(lock_path):
        pass

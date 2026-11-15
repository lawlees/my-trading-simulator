
"""Exclusive process-level lock for the Schwab OAuth worker.

The lock must be acquired before initializing the Schwab client
and held until the worker shuts down.
"""

import fcntl
from pathlib import Path


class SchwabWorkerLock:
    """Prevent concurrent Schwab workers on the same Linux host."""

    def __init__(self, lock_path: str | Path):
        self.lock_path = Path(lock_path)
        self._file = None

    def acquire(self) -> None:
        if self._file is not None:
            raise RuntimeError("Schwab worker lock already acquired")

        self.lock_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        lock_file = self.lock_path.open("a+")

        try:
            fcntl.flock(
                lock_file.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError:
            lock_file.close()
            raise RuntimeError(
                "Another Schwab worker is already running"
            ) from None
        except Exception:
            lock_file.close()
            raise

        self._file = lock_file

    def release(self) -> None:
        if self._file is None:
            return

        try:
            fcntl.flock(
                self._file.fileno(),
                fcntl.LOCK_UN,
            )
        finally:
            self._file.close()
            self._file = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()
        return False

"""Entrypoint for the isolated, read-only Schwab market-data socket service.

This module exposes no brokerage order operations. It does not start a worker
when imported. The host's service manager is responsible for running it as
schwab-worker, with the restricted OAuth/token filesystem and AWS profile.
"""

import argparse
import logging
import os
import pwd
import signal
import threading

from my_trading_simulator.market_data.socket_directory_security import (
    validate_socket_directory,
)
from my_trading_simulator.market_data.socket_protocol import SOCKET_PATH
from my_trading_simulator.market_data.socket_server import MarketDataSocketServer

LOGGER = logging.getLogger(__name__)


def check_service_identity(username: str = "schwab-worker") -> None:
    """Refuse to serve from the wrong Unix account, including root."""
    try:
        uid = pwd.getpwnam(username).pw_uid
    except KeyError as exc:
        raise RuntimeError("Dedicated Schwab account unavailable") from exc
    if os.geteuid() != uid:
        raise RuntimeError("Market-data service must run as schwab-worker")


def check_service_configuration() -> None:
    """Check filesystem/identity only; never touch OAuth or Schwab."""
    check_service_identity()
    validate_socket_directory(os.path.dirname(SOCKET_PATH))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Schwab IPC service")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check-config", action="store_true")
    group.add_argument("--serve", action="store_true")
    args = parser.parse_args(argv)
    check_service_configuration()

    if args.check_config:
        print("Schwab IPC service configuration: PASSED")
        print("Schwab API requests: NONE")
        print("Brokerage orders: DISABLED")
        return 0

    stop_event = threading.Event()

    def request_stop(signum, frame):
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    LOGGER.info("Starting local-only read-only Schwab market-data service")
    MarketDataSocketServer().serve(stop_event=stop_event)
    LOGGER.info("Read-only Schwab market-data service stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

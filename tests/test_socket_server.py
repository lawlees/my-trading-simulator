"""End-to-end socket server tests using fake market data."""

import threading
import time
import uuid
from pathlib import Path

from my_trading_simulator.market_data.socket_client import (
    MarketDataSocketClient,
)
from my_trading_simulator.market_data.socket_server import (
    MarketDataSocketServer,
)


class FakeSchwabClient:
    def get_stock_quote(self, symbol):
        return {
            symbol: {
                "symbol": symbol,
                "lastPrice": 600.0,
            }
        }


def test_socket_server_end_to_end(tmp_path):
    # Keep the AF_UNIX path short enough for macOS.
    path = Path("/tmp") / (
        f"md-{uuid.uuid4().hex[:12]}.sock"
    )

    lock_path = tmp_path / "worker.lock"

    server = MarketDataSocketServer(
        socket_path=path,
        client_factory=FakeSchwabClient,
        directory_validator=lambda directory: None,
        peer_authorizer=lambda connection: 1000,
        lock_path=lock_path,
    )

    thread = threading.Thread(
        target=server.serve,
        kwargs={"max_connections": 1},
        daemon=True,
    )

    try:
        thread.start()

        for _ in range(100):
            if path.exists():
                break
            time.sleep(0.01)

        assert path.exists()

        client = MarketDataSocketClient(
            socket_path=str(path),
            timeout_seconds=2,
        )

        result = client.get_stock_quote("SPY")

        assert result["SPY"]["symbol"] == "SPY"
        assert result["SPY"]["lastPrice"] == 600.0

        thread.join(timeout=5)

        assert not thread.is_alive()
        assert not path.exists()
    finally:
        thread.join(timeout=5)

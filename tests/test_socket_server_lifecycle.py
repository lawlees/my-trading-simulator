"""Shutdown and multi-request behavior for isolated socket listener."""

import threading
import time
import uuid
from pathlib import Path

from my_trading_simulator.market_data.socket_client import MarketDataSocketClient
from my_trading_simulator.market_data.socket_server import MarketDataSocketServer


def test_shutdown_after_multiple_readonly_requests(tmp_path):
    path = Path('/tmp') / f'mdlife-{uuid.uuid4().hex[:10]}.sock'
    stop = threading.Event()

    class FakeClient:
        def get_stock_quote(self, symbol):
            return {symbol: {"symbol": symbol}}

    server = MarketDataSocketServer(
        socket_path=path,
        lock_path=tmp_path / 'worker.lock',
        directory_validator=lambda directory: None,
        peer_authorizer=lambda connection: 1,
        client_factory=FakeClient,
    )
    thread = threading.Thread(target=server.serve, kwargs={'stop_event': stop}, daemon=True)
    try:
        thread.start()
        for _ in range(200):
            if path.exists():
                break
            time.sleep(.01)
        assert path.exists()
        client = MarketDataSocketClient(socket_path=str(path))

        # bind() creates the socket path before listen() completes.
        # Retry only the initial connection while the server starts.
        from my_trading_simulator.market_data.socket_client import (
            MarketDataSocketError,
        )

        deadline = time.monotonic() + 3
        while True:
            try:
                quote = client.get_stock_quote('SPY')
                break
            except MarketDataSocketError:
                if time.monotonic() >= deadline or not thread.is_alive():
                    raise
                time.sleep(0.01)

        assert quote['SPY']['symbol'] == 'SPY'
        assert client.get_stock_quote('QQQ')['QQQ']['symbol'] == 'QQQ'
    finally:
        stop.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert not path.exists()

"""Verify unauthorized socket peers cannot access market data."""

import socket
import threading
import time
import uuid
from pathlib import Path

from my_trading_simulator.market_data.socket_server import (
    MarketDataSocketServer,
)
from my_trading_simulator.market_data.socket_peer_auth import (
    PeerAuthorizationError,
)


def test_unauthorized_peer_cannot_initialize_schwab(tmp_path):
    path = Path("/tmp") / f"md-auth-{uuid.uuid4().hex[:10]}.sock"

    client_initializations = []

    class FakeSchwabClient:
        def __init__(self):
            client_initializations.append(True)

        def get_stock_quote(self, symbol):
            raise AssertionError("Unauthorized market-data access")

    def reject_peer(connection):
        raise PeerAuthorizationError("Unauthorized socket peer")

    server = MarketDataSocketServer(
        socket_path=path,
        client_factory=FakeSchwabClient,
        directory_validator=lambda directory: None,
        lock_path=tmp_path / "worker.lock",
        peer_authorizer=reject_peer,
    )

    stop_event = threading.Event()

    thread = threading.Thread(
        target=server.serve,
        kwargs={"stop_event": stop_event},
        daemon=True,
    )

    thread.start()

    try:
        for _ in range(100):
            if path.exists():
                break
            time.sleep(0.01)

        assert path.exists()

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2)
            client.connect(str(path))

            try:
                client.sendall(
                    b'{"operation":"stock_quote","symbol":"SPY"}\n'
                )
                response = client.recv(4096)
                assert response == b""
            except (BrokenPipeError, ConnectionResetError):
                pass

        # An unauthorized connection must never initialize Schwab.
        assert client_initializations == []

    finally:
        stop_event.set()
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert not path.exists()

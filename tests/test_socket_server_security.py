"""Security tests for the local Schwab socket server."""

import json
import socket
import threading
import time

import pytest

from my_trading_simulator.market_data.socket_server import (
    MarketDataSocketServer,
)


def test_existing_file_is_not_replaced(tmp_path):
    path = tmp_path / "existing.sock"
    path.write_text("DO NOT DELETE")

    server = MarketDataSocketServer(socket_path=path)

    with pytest.raises(RuntimeError, match="already exists"):
        server.serve(max_connections=1)

    assert path.read_text() == "DO NOT DELETE"


def test_symlink_is_rejected(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("PROTECTED")

    path = tmp_path / "schwab.sock"
    path.symlink_to(target)

    server = MarketDataSocketServer(socket_path=path)

    with pytest.raises(RuntimeError, match="symlink"):
        server.serve(max_connections=1)

    assert target.read_text() == "PROTECTED"
    assert path.is_symlink()


def test_unauthorized_operation_never_reaches_client(tmp_path):
    import uuid
    from pathlib import Path

    path = Path("/tmp") / f"mdsec-{uuid.uuid4().hex[:10]}.sock"
    lock_path = tmp_path / "worker.lock"

    calls = []

    class FakeClient:
        def __init__(self):
            calls.append("initialized")

        def get_stock_quote(self, symbol):
            calls.append(("quote", symbol))
            return {}

    server = MarketDataSocketServer(
        socket_path=path,
        client_factory=FakeClient,
        directory_validator=lambda directory: None,
        peer_authorizer=lambda connection: 1000,
        lock_path=lock_path,
    )

    thread = threading.Thread(
        target=server.serve,
        kwargs={"max_connections": 1},
        daemon=True,
    )

    thread.start()

    try:
        for _ in range(100):
            if path.exists():
                break
            time.sleep(0.01)

        assert path.exists()

        with socket.socket(
            socket.AF_UNIX, socket.SOCK_STREAM
        ) as connection:
            connection.settimeout(3)
            connection.connect(str(path))
            connection.sendall(
                b'{"operation":"place_order","symbol":"SPY"}\n'
            )

            response = bytearray()
            while b"\n" not in response:
                chunk = connection.recv(4096)
                if not chunk:
                    break
                response.extend(chunk)

        decoded = json.loads(response)
        assert decoded["status"] == "error"
        assert calls == []

    finally:
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert not path.exists()

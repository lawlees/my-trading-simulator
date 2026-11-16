"""Tests for the read-only Unix socket client."""

import json
import socket
import threading
import uuid
from pathlib import Path

import pytest

from my_trading_simulator.market_data.socket_client import (
    MarketDataSocketClient,
    MarketDataSocketError,
)
from my_trading_simulator.market_data.socket_protocol import (
    MarketDataRequestError,
    MAX_RESPONSE_BYTES,
)


def start_fake_server(socket_path, response):
    """Start a fake server that returns one response."""

    ready = threading.Event()
    errors = []

    def serve():
        try:
            with socket.socket(
                socket.AF_UNIX, socket.SOCK_STREAM
            ) as server:
                server.bind(str(socket_path))
                server.listen(1)
                ready.set()

                connection, _ = server.accept()

                with connection:
                    connection.settimeout(2)
                    received = bytearray()

                    while b"\n" not in received:
                        chunk = connection.recv(4096)
                        if not chunk:
                            break
                        received.extend(chunk)

                    connection.sendall(response)
        except Exception as error:
            errors.append(error)
            ready.set()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    assert ready.wait(timeout=3)
    assert not errors

    return thread, errors


def test_stock_quote_success(tmp_path):
    path = Path("/tmp") / f"schwab-{uuid.uuid4().hex[:12]}.sock"

    response = json.dumps({
        "status": "success",
        "data": {"SPY": {"symbol": "SPY"}},
    }).encode() + b"\n"

    thread, errors = start_fake_server(path, response)

    client = MarketDataSocketClient(
        socket_path=str(path),
        timeout_seconds=2,
    )

    result = client.get_stock_quote("SPY")

    assert result["SPY"]["symbol"] == "SPY"

    thread.join(timeout=3)
    assert not errors


def test_worker_rejection(tmp_path):
    path = Path("/tmp") / f"schwab-{uuid.uuid4().hex[:12]}.sock"

    response = json.dumps({
        "status": "error",
        "message": "Request rejected",
    }).encode() + b"\n"

    thread, errors = start_fake_server(path, response)

    client = MarketDataSocketClient(
        socket_path=str(path),
        timeout_seconds=2,
    )

    with pytest.raises(
        MarketDataSocketError,
        match="rejected",
    ):
        client.get_stock_quote("SPY")

    thread.join(timeout=3)
    assert not errors


def test_invalid_symbol_never_connects(tmp_path):
    path = tmp_path / "missing.sock"

    client = MarketDataSocketClient(
        socket_path=str(path)
    )

    with pytest.raises(MarketDataRequestError):
        client.get_stock_quote("AAPL")


def test_missing_socket_fails_closed(tmp_path):
    client = MarketDataSocketClient(
        socket_path=str(tmp_path / "missing.sock"),
        timeout_seconds=1,
    )

    with pytest.raises(
        MarketDataSocketError,
        match="unavailable",
    ):
        client.get_stock_quote("SPY")


def test_malformed_response_rejected(tmp_path):
    path = Path("/tmp") / f"schwab-{uuid.uuid4().hex[:12]}.sock"

    thread, errors = start_fake_server(
        path,
        b"not-json\n",
    )

    client = MarketDataSocketClient(
        socket_path=str(path),
        timeout_seconds=2,
    )

    with pytest.raises(
        MarketDataSocketError,
        match="Invalid market-data response",
    ):
        client.get_stock_quote("SPY")

    thread.join(timeout=3)
    assert not errors


def test_oversized_response_rejected(tmp_path):
    path = Path("/tmp") / f"schwab-{uuid.uuid4().hex[:12]}.sock"

    response = b"x" * (MAX_RESPONSE_BYTES + 1)

    thread, errors = start_fake_server(path, response)

    client = MarketDataSocketClient(
        socket_path=str(path),
        timeout_seconds=2,
    )

    with pytest.raises(
        MarketDataSocketError,
        match="Response too large",
    ):
        client.get_stock_quote("SPY")

    thread.join(timeout=3)
    assert not errors

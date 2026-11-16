"""Tests for the read-only socket request handler."""

import json
import socket
import threading

import pytest

from my_trading_simulator.market_data.socket_handler import (
    handle_market_data_connection,
)


def exchange(payload, operation):
    """Exchange one message over an in-memory socket pair."""

    client, server = socket.socketpair()
    thread = threading.Thread(
        target=handle_market_data_connection,
        args=(server, operation),
        daemon=True,
    )

    thread.start()

    try:
        client.settimeout(3.0)
        client.sendall(payload)
        client.shutdown(socket.SHUT_WR)

        response = bytearray()

        while b"\n" not in response:
            chunk = client.recv(4096)
            if not chunk:
                break
            response.extend(chunk)

        return json.loads(response)
    finally:
        client.close()
        thread.join(timeout=6)
        server.close()
        assert not thread.is_alive()


def test_valid_request():
    calls = []

    def operation(request):
        calls.append(request)
        return {"SPY": {"symbol": "SPY"}}

    result = exchange(
        b'{"operation":"stock_quote","symbol":"SPY"}\n',
        operation,
    )

    assert result["status"] == "success"
    assert result["data"]["SPY"]["symbol"] == "SPY"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        b'not-json\n',
        b'{"operation":"place_order","symbol":"SPY"}\n',
        b'{"operation":"stock_quote","symbol":"AAPL"}\n',
        b'{"operation":"stock_quote","symbol":"SPY"}\nextra',
        b"x" * 5000 + b"\n",
    ],
)
def test_invalid_request_never_dispatched(payload):
    calls = []

    def operation(request):
        calls.append(request)
        return {}

    result = exchange(payload, operation)

    assert result["status"] == "error"
    assert calls == []


def test_operation_failure_is_hidden():
    def operation(request):
        raise RuntimeError("Sensitive internal details")

    result = exchange(
        b'{"operation":"stock_quote","symbol":"SPY"}\n',
        operation,
    )

    assert result["status"] == "error"
    assert "Sensitive internal details" not in str(result)


def test_non_serializable_response_rejected():
    result = exchange(
        b'{"operation":"stock_quote","symbol":"SPY"}\n',
        lambda request: {"value": object()},
    )

    assert result["status"] == "error"

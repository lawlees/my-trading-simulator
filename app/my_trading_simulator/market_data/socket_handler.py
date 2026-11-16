"""Handle one read-only market-data socket request."""

import json
import socket

from my_trading_simulator.market_data.socket_protocol import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    MarketDataRequestError,
    validate_market_data_request,
)


def handle_market_data_connection(
    connection: socket.socket,
    operation,
) -> None:
    """
    Handle one socket request.

    operation receives an already validated request.
    The future worker server is responsible for locking
    and Schwab client initialization.
    """

    connection.settimeout(5.0)

    try:
        received = bytearray()

        while b"\n" not in received:
            remaining = MAX_REQUEST_BYTES + 1 - len(received)

            if remaining <= 0:
                raise MarketDataRequestError(
                    "Request too large"
                )

            chunk = connection.recv(min(4096, remaining))

            if not chunk:
                raise MarketDataRequestError(
                    "Incomplete request"
                )

            received.extend(chunk)

            if len(received) > MAX_REQUEST_BYTES:
                raise MarketDataRequestError(
                    "Request too large"
                )

        raw, extra = bytes(received).split(b"\n", 1)

        if extra:
            raise MarketDataRequestError(
                "Unexpected request data"
            )

        try:
            request = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise MarketDataRequestError(
                "Invalid JSON"
            ) from None

        validated = validate_market_data_request(request)

        result = operation(validated)

        if not isinstance(result, dict):
            raise ValueError("Invalid operation response")

        response = {
            "status": "success",
            "data": result,
        }

        encoded = (
            json.dumps(
                response,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            + b"\n"
        )

        if len(encoded) > MAX_RESPONSE_BYTES:
            raise ValueError("Response too large")

    except (
        MarketDataRequestError,
        ValueError,
        TypeError,
        OSError,
        TimeoutError,
    ):
        response = {
            "status": "error",
            "message": "Market-data request rejected",
        }

        encoded = (
            json.dumps(response).encode("utf-8") + b"\n"
        )

    except Exception:
        # Fail closed without exposing internal errors.
        response = {
            "status": "error",
            "message": "Market-data worker failure",
        }

        encoded = (
            json.dumps(response).encode("utf-8") + b"\n"
        )

    try:
        connection.sendall(encoded)
    except OSError:
        pass

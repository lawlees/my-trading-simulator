"""Restricted Unix socket client for read-only market data."""

import json
import socket

from my_trading_simulator.market_data.socket_protocol import (
    SOCKET_PATH,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    MarketDataRequestError,
    validate_market_data_request,
)


class MarketDataSocketError(RuntimeError):
    """Market-data socket communication failed."""


class MarketDataSocketClient:
    def __init__(
        self,
        socket_path: str = SOCKET_PATH,
        timeout_seconds: float = 5.0,
    ):
        if not 0 < timeout_seconds <= 30:
            raise ValueError("Invalid socket timeout")

        self.socket_path = socket_path
        self.timeout_seconds = timeout_seconds

    def _request(self, payload: dict) -> dict:
        validated = validate_market_data_request(payload)

        encoded = (
            json.dumps(validated, separators=(",", ":")).encode()
            + b"\n"
        )

        if len(encoded) > MAX_REQUEST_BYTES:
            raise MarketDataSocketError("Request too large")

        try:
            with socket.socket(
                socket.AF_UNIX, socket.SOCK_STREAM
            ) as connection:
                connection.settimeout(self.timeout_seconds)
                connection.connect(self.socket_path)
                connection.sendall(encoded)

                chunks = bytearray()

                while True:
                    remaining = MAX_RESPONSE_BYTES + 1 - len(chunks)

                    if remaining <= 0:
                        raise MarketDataSocketError(
                            "Response too large"
                        )

                    data = connection.recv(
                        min(65536, remaining)
                    )

                    if not data:
                        raise MarketDataSocketError(
                            "Connection closed before response"
                        )

                    chunks.extend(data)

                    if len(chunks) > MAX_RESPONSE_BYTES:
                        raise MarketDataSocketError(
                            "Response too large"
                        )

                    if b"\n" in data:
                        break

        except (OSError, TimeoutError) as error:
            raise MarketDataSocketError(
                "Market-data worker unavailable"
            ) from error

        try:
            raw, extra = bytes(chunks).split(b"\n", 1)

            if extra:
                raise ValueError("Unexpected response data")

            response = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as error:
            raise MarketDataSocketError(
                "Invalid market-data response"
            ) from error

        if not isinstance(response, dict):
            raise MarketDataSocketError(
                "Invalid response structure"
            )

        if response.get("status") != "success":
            raise MarketDataSocketError(
                "Market-data request rejected"
            )

        result = response.get("data")

        if not isinstance(result, dict):
            raise MarketDataSocketError(
                "Invalid market-data payload"
            )

        return result

    def get_stock_quote(self, symbol: str) -> dict:
        return self._request({
            "operation": "stock_quote",
            "symbol": symbol,
        })

    def get_0dte_option_chain(
        self,
        symbol: str,
        trading_date,
        strike_count: int = 10,
    ) -> dict:
        return self._request({
            "operation": "option_chain",
            "symbol": symbol,
            "trading_date": trading_date.isoformat(),
            "strike_count": strike_count,
        })

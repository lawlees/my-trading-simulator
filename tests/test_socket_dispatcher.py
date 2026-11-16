"""Tests for read-only Schwab request dispatch."""

from datetime import date

import pytest

from my_trading_simulator.market_data.socket_dispatcher import (
    dispatch_market_data_request,
)
from my_trading_simulator.market_data.socket_protocol import (
    MarketDataRequestError,
)


class FakeMarketDataClient:
    def __init__(self):
        self.calls = []

    def get_stock_quote(self, symbol):
        self.calls.append(("stock_quote", symbol))
        return {"symbol": symbol}

    def get_0dte_option_chain(
        self, symbol, trading_date, strike_count
    ):
        self.calls.append(
            ("option_chain", symbol, trading_date, strike_count)
        )
        return {"symbol": symbol, "status": "SUCCESS"}


def test_dispatch_stock_quote():
    client = FakeMarketDataClient()

    result = dispatch_market_data_request(
        client,
        {"operation": "stock_quote", "symbol": "SPY"},
    )

    assert result == {"symbol": "SPY"}
    assert client.calls == [("stock_quote", "SPY")]


def test_dispatch_option_chain():
    client = FakeMarketDataClient()

    result = dispatch_market_data_request(
        client,
        {
            "operation": "option_chain",
            "symbol": "QQQ",
            "trading_date": "2026-11-16",
            "strike_count": 10,
        },
    )

    assert result["status"] == "SUCCESS"
    assert client.calls == [
        ("option_chain", "QQQ", date(2026, 11, 16), 10)
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"operation": "place_order", "symbol": "SPY"},
        {"operation": "stock_quote", "symbol": "AAPL"},
        {"operation": "stock_quote", "symbol": "SPY", "extra": 1},
    ],
)
def test_unsafe_requests_never_reach_client(payload):
    client = FakeMarketDataClient()

    with pytest.raises(MarketDataRequestError):
        dispatch_market_data_request(client, payload)

    assert client.calls == []

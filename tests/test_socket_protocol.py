"""Tests for restricted Schwab market-data socket requests."""

import pytest

from my_trading_simulator.market_data.socket_protocol import (
    MarketDataRequestError,
    validate_market_data_request,
)


def test_valid_stock_quote():
    assert validate_market_data_request({
        "operation": "stock_quote",
        "symbol": "SPY",
    }) == {
        "operation": "stock_quote",
        "symbol": "SPY",
    }


def test_valid_option_chain():
    request = {
        "operation": "option_chain",
        "symbol": "QQQ",
        "trading_date": "2026-11-16",
        "strike_count": 10,
    }
    assert validate_market_data_request(request) == request


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"operation": "place_order", "symbol": "SPY"},
        {"operation": "stock_quote", "symbol": "AAPL"},
        {"operation": "stock_quote", "symbol": "spy"},
        {"operation": "stock_quote", "symbol": "SPY", "extra": 1},
        {
            "operation": "option_chain",
            "symbol": "SPY",
            "trading_date": "bad-date",
            "strike_count": 10,
        },
        {
            "operation": "option_chain",
            "symbol": "SPY",
            "trading_date": "2026-11-16",
            "strike_count": True,
        },
        {
            "operation": "option_chain",
            "symbol": "SPY",
            "trading_date": "2026-11-16",
            "strike_count": 100,
        },
        {
            "operation": "option_chain",
            "symbol": "SPY",
            "trading_date": "2026-11-16",
            "strike_count": 0,
        },
    ],
)
def test_invalid_requests_rejected(payload):
    with pytest.raises(MarketDataRequestError):
        validate_market_data_request(payload)

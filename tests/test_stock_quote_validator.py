
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from my_trading_simulator.market_data.stock_quote_validator import (
    validate_stock_quote,
)


NOW = datetime(
    2026, 11, 12, 15, 0, 0,
    tzinfo=timezone.utc,
)


def timestamp_ms(dt):
    return int(dt.timestamp() * 1000)


def make_quote(
    bid=758.99,
    ask=759.06,
    quote_time="DEFAULT",
    symbol="SPY",
):
    if quote_time == "DEFAULT":
        quote_time = timestamp_ms(NOW)

    return {
        symbol: {
            "quote": {
                "bidPrice": bid,
                "askPrice": ask,
                "quoteTime": quote_time,
            }
        }
    }


def test_valid_quote_returns_midpoint():
    price, reason = validate_stock_quote(
        response=make_quote(),
        symbol="SPY",
        now=NOW,
    )

    assert price == Decimal("759.025")
    assert reason == "Stock quote is valid"


@pytest.mark.parametrize(
    "age_seconds, expected_valid",
    [
        (0, True),
        (5, True),
        (10, True),
        (11, False),
        (30, False),
        (-2, True),
        (-3, False),
    ],
)
def test_quote_freshness(
    age_seconds,
    expected_valid,
):
    quote_time = timestamp_ms(
        NOW - timedelta(seconds=age_seconds)
    )

    price, _ = validate_stock_quote(
        response=make_quote(quote_time=quote_time),
        symbol="SPY",
        now=NOW,
    )

    assert (price is not None) is expected_valid


@pytest.mark.parametrize(
    "bid, ask",
    [
        (0, 759.06),
        (-1, 759.06),
        (758.99, 0),
        (758.99, -1),
        (760, 759),
        ("NaN", 759.06),
        (758.99, "Infinity"),
        ("invalid", 759.06),
    ],
)
def test_rejects_invalid_prices(
    bid,
    ask,
):
    price, _ = validate_stock_quote(
        response=make_quote(bid=bid, ask=ask),
        symbol="SPY",
        now=NOW,
    )

    assert price is None


@pytest.mark.parametrize(
    "timestamp",
    [
        0,
        -1,
        "invalid",
        None,
        True,
    ],
)
def test_rejects_invalid_timestamps(timestamp):
    price, _ = validate_stock_quote(
        response=make_quote(quote_time=timestamp),
        symbol="SPY",
        now=NOW,
    )

    assert price is None


def test_missing_timestamp():
    response = make_quote()
    del response["SPY"]["quote"]["quoteTime"]

    price, _ = validate_stock_quote(
        response=response,
        symbol="SPY",
        now=NOW,
    )

    assert price is None


def test_missing_symbol():
    price, _ = validate_stock_quote(
        response={},
        symbol="SPY",
        now=NOW,
    )

    assert price is None


def test_unsupported_symbol():
    price, _ = validate_stock_quote(
        response=make_quote(),
        symbol="AAPL",
        now=NOW,
    )

    assert price is None


@pytest.mark.parametrize(
    "symbol",
    ["SPY", "QQQ", "IWM"],
)
def test_supported_symbols(symbol):
    price, _ = validate_stock_quote(
        response=make_quote(symbol=symbol),
        symbol=symbol,
        now=NOW,
    )

    assert price == Decimal("759.025")


def test_rejects_naive_datetime():
    naive_now = datetime(2026, 11, 12, 15, 0, 0)

    price, _ = validate_stock_quote(
        response=make_quote(),
        symbol="SPY",
        now=naive_now,
    )

    assert price is None

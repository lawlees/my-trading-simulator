
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from my_trading_simulator.market_data.strike_safety import (
    validate_strike_with_stock_quote,
)


NOW = datetime(
    2026, 11, 12, 15, 0, 0,
    tzinfo=timezone.utc,
)


def make_stock_quote(
    bid=759,
    ask=761,
    age_seconds=0,
    symbol="SPY",
):
    timestamp_ms = int(
        (
            NOW - timedelta(seconds=age_seconds)
        ).timestamp() * 1000
    )

    return {
        symbol: {
            "quote": {
                "bidPrice": bid,
                "askPrice": ask,
                "quoteTime": timestamp_ms,
            }
        }
    }


@pytest.mark.parametrize(
    "strike, expected",
    [
        ("760", True),
        ("750", True),
        ("745", True),
        ("740", False),
        ("650", False),
        ("775", True),
        ("780", False),
    ],
)
def test_strike_safety_with_valid_quote(
    strike,
    expected,
):
    valid, _ = validate_strike_with_stock_quote(
        strike_price=Decimal(strike),
        symbol="SPY",
        stock_quote_response=make_stock_quote(),
        now=NOW,
    )

    assert valid is expected


@pytest.mark.parametrize(
    "age_seconds",
    [11, 30, 60],
)
def test_rejects_stale_stock_quote(age_seconds):
    valid, reason = validate_strike_with_stock_quote(
        strike_price=Decimal("760"),
        symbol="SPY",
        stock_quote_response=make_stock_quote(
            age_seconds=age_seconds
        ),
        now=NOW,
    )

    assert valid is False
    assert "stale" in reason.lower()


def test_rejects_missing_stock_quote():
    valid, _ = validate_strike_with_stock_quote(
        strike_price=Decimal("760"),
        symbol="SPY",
        stock_quote_response={},
        now=NOW,
    )

    assert valid is False


def test_rejects_invalid_stock_price():
    valid, _ = validate_strike_with_stock_quote(
        strike_price=Decimal("760"),
        symbol="SPY",
        stock_quote_response=make_stock_quote(
            bid=0,
            ask=761,
        ),
        now=NOW,
    )

    assert valid is False


@pytest.mark.parametrize(
    "symbol",
    ["SPY", "QQQ", "IWM"],
)
def test_supported_underlyings(symbol):
    valid, _ = validate_strike_with_stock_quote(
        strike_price=Decimal("750"),
        symbol=symbol,
        stock_quote_response=make_stock_quote(
            symbol=symbol
        ),
        now=NOW,
    )

    assert valid is True


def test_rejects_unsupported_underlying():
    valid, _ = validate_strike_with_stock_quote(
        strike_price=Decimal("750"),
        symbol="AAPL",
        stock_quote_response=make_stock_quote(),
        now=NOW,
    )

    assert valid is False

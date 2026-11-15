"""Standalone read-only quote-adapter tests; no Schwab calls or DB writes."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from my_trading_simulator.market_data.held_option_quote import (
    validated_held_option_bid,
)

NOW = datetime(2026, 11, 13, 16, 0, tzinfo=timezone.utc)
SYMBOL = "SPY   261113C00600000"


def position(**overrides):
    values = dict(option_symbol=SYMBOL, symbol="SPY", option_type="CALL",
                  expiration_date=NOW.date(), strike_price=Decimal("600"),
                  status="OPEN", remaining_quantity=4)
    values.update(overrides)
    return SimpleNamespace(**values)


def quote(**overrides):
    values = {"bidPrice": 0.40, "askPrice": 0.42,
              "quoteTime": int(NOW.timestamp() * 1000)}
    values.update(overrides)
    return {"quote": values}


def test_fresh_exact_quote_returns_bid():
    bid, reason = validated_held_option_bid(position(), quote(), now=NOW)
    assert bid == Decimal("0.4"), reason


def test_stale_quote_rejected():
    bid, _ = validated_held_option_bid(
        position(), quote(quoteTime=int(NOW.timestamp() * 1000) - 12000), now=NOW)
    assert bid is None


def test_spread_rejected():
    bid, _ = validated_held_option_bid(position(), quote(askPrice=1.0), now=NOW)
    assert bid is None


def test_wrong_contract_strike_rejected():
    bid, _ = validated_held_option_bid(position(strike_price=Decimal("605")), quote(), now=NOW)
    assert bid is None


def test_wrong_returned_symbol_rejected():
    data = quote()
    data["symbol"] = "QQQ   261113C00600000"
    bid, _ = validated_held_option_bid(position(), data, now=NOW)
    assert bid is None


def test_missing_timestamp_rejected():
    bid, _ = validated_held_option_bid(position(), {"quote": {"bidPrice": 0.4, "askPrice": 0.42}}, now=NOW)
    assert bid is None


def test_nonfinite_price_rejected():
    bid, _ = validated_held_option_bid(position(), quote(bidPrice="NaN"), now=NOW)
    assert bid is None


def test_legacy_missing_symbol_rejected():
    bid, _ = validated_held_option_bid(position(option_symbol=None), quote(), now=NOW)
    assert bid is None


def test_closed_position_rejected():
    bid, _ = validated_held_option_bid(position(status="CLOSED"), quote(), now=NOW)
    assert bid is None

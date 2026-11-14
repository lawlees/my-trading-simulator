
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from my_trading_simulator.market_data.contract_selector import (
    OptionContract,
)
from my_trading_simulator.market_data.quote_validator import (
    validate_option_quote,
    validate_contract_for_paper_trade,
)


TRADING_DATE = date(2026, 11, 12)

NOW = datetime(
    2026, 11, 12, 15, 0, 0,
    tzinfo=timezone.utc,
)


def make_contract(
    bid=Decimal("0.45"),
    ask=Decimal("0.48"),
    expiration_date=TRADING_DATE,
):
    return OptionContract(
        symbol="SPY   261112P00758000",
        underlying_symbol="SPY",
        option_type="PUT",
        expiration_date=expiration_date,
        strike_price=Decimal("758"),
        bid=bid,
        ask=ask,
        volume=100,
    )


def timestamp_ms(dt):
    return int(dt.timestamp() * 1000)


def test_valid_quote():
    valid, reason = validate_option_quote(
        contract=make_contract(),
        quote_timestamp_ms=timestamp_ms(NOW),
        trading_date=TRADING_DATE,
        now=NOW,
    )

    assert valid is True
    assert reason == "Quote is valid"


def test_stale_quote_is_rejected():
    valid, reason = validate_option_quote(
        contract=make_contract(),
        quote_timestamp_ms=timestamp_ms(
            NOW - timedelta(seconds=30)
        ),
        trading_date=TRADING_DATE,
        now=NOW,
    )

    assert valid is False
    assert reason == "Quote is stale"


def test_wide_spread_is_rejected():
    valid, reason = validate_option_quote(
        contract=make_contract(
            bid=Decimal("0.20"),
            ask=Decimal("0.50"),
        ),
        quote_timestamp_ms=timestamp_ms(NOW),
        trading_date=TRADING_DATE,
        now=NOW,
    )

    assert valid is False
    assert reason == "Bid/ask spread too wide"


def test_wrong_expiration_is_rejected():
    valid, reason = validate_option_quote(
        contract=make_contract(
            expiration_date=date(2026, 11, 13)
        ),
        quote_timestamp_ms=timestamp_ms(NOW),
        trading_date=TRADING_DATE,
        now=NOW,
    )

    assert valid is False
    assert reason == "Contract is not 0DTE"


def test_future_quote_is_rejected():
    valid, reason = validate_option_quote(
        contract=make_contract(),
        quote_timestamp_ms=timestamp_ms(
            NOW + timedelta(seconds=30)
        ),
        trading_date=TRADING_DATE,
        now=NOW,
    )

    assert valid is False
    assert reason == "Quote timestamp is in the future"


def test_invalid_bid_ask_is_rejected():
    valid, reason = validate_option_quote(
        contract=make_contract(
            bid=Decimal("0.60"),
            ask=Decimal("0.50"),
        ),
        quote_timestamp_ms=timestamp_ms(NOW),
        trading_date=TRADING_DATE,
        now=NOW,
    )

    assert valid is False
    assert reason == "Bid exceeds ask"


def test_missing_timestamp_is_rejected():
    valid, reason = validate_option_quote(
        contract=make_contract(),
        quote_timestamp_ms=None,
        trading_date=TRADING_DATE,
        now=NOW,
    )

    assert valid is False
    assert reason == "Missing or invalid quote timestamp"


def test_paper_trade_rejects_missing_schwab_timestamp():
    contract = make_contract()

    # Existing test contracts have no Schwab timestamp.
    assert contract.quote_timestamp_ms is None

    valid, reason = validate_contract_for_paper_trade(
        contract=contract,
        trading_date=TRADING_DATE,
        now=NOW,
    )

    assert valid is False
    assert reason == "Missing or invalid quote timestamp"


def test_paper_trade_rejects_stale_schwab_timestamp():
    from dataclasses import replace

    contract = replace(
        make_contract(),
        quote_timestamp_ms=timestamp_ms(
            NOW - timedelta(seconds=30)
        ),
    )

    valid, reason = validate_contract_for_paper_trade(
        contract=contract,
        trading_date=TRADING_DATE,
        now=NOW,
    )

    assert valid is False
    assert reason == "Quote is stale"


def test_paper_trade_accepts_fresh_schwab_timestamp():
    from dataclasses import replace

    contract = replace(
        make_contract(),
        quote_timestamp_ms=timestamp_ms(NOW),
    )

    valid, reason = validate_contract_for_paper_trade(
        contract=contract,
        trading_date=TRADING_DATE,
        now=NOW,
    )

    assert valid is True
    assert reason == "Quote is valid"


import pytest


@pytest.mark.parametrize(
    "bad_timestamp",
    [
        "1794518100312",
        -1,
        0,
        True,
        999999999999999999999,
    ],
)
def test_paper_trade_rejects_malformed_timestamp(
    bad_timestamp,
):
    from dataclasses import replace

    contract = replace(
        make_contract(),
        quote_timestamp_ms=bad_timestamp,
    )

    valid, reason = validate_contract_for_paper_trade(
        contract=contract,
        trading_date=TRADING_DATE,
        now=NOW,
    )

    assert valid is False
    assert reason == "Missing or invalid quote timestamp"

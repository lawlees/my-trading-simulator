
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from my_trading_simulator.config.settings import settings
from my_trading_simulator.market_data.validated_selector import (
    find_valid_fallback_contract,
    find_valid_explicit_contract,
    find_valid_contract_by_symbol,
)


TRADING_DATE = date(2026, 11, 12)

NOW = datetime(
    2026, 11, 12, 15, 0, 0,
    tzinfo=timezone.utc,
)


def timestamp_ms(dt):
    return int(dt.timestamp() * 1000)


def make_valid_stock_quote():
    """
    Create a fresh SPY quote for selector tests.
    """
    return {
        "SPY": {
            "quote": {
                "bidPrice": 759,
                "askPrice": 761,
                "quoteTime": timestamp_ms(NOW),
            }
        }
    }


def make_chain():
    return {
        "symbol": "SPY",
        "callExpDateMap": {
            "2026-11-12:0": {
                "760.0": [
                    {
                        "symbol": "SPY 261112C00760000",
                        "bid": 0.43,
                        "ask": 0.45,
                        "totalVolume": 100,
                        "quoteTimeInLong": timestamp_ms(
                            NOW - timedelta(seconds=30)
                        ),
                    }
                ],
                "761.0": [
                    {
                        "symbol": "SPY 261112C00761000",
                        "bid": 0.44,
                        "ask": 0.48,
                        "totalVolume": 100,
                        "quoteTimeInLong": timestamp_ms(NOW),
                    }
                ],
            }
        },
        "putExpDateMap": {},
    }


def test_skips_stale_contract_and_selects_fresh_one():
    contract = find_valid_fallback_contract(
        chain=make_chain(),
        option_type="CALL",
        trading_date=TRADING_DATE,
        now=NOW,
    )

    assert contract is not None
    assert contract.symbol == "SPY 261112C00761000"
    assert contract.ask == Decimal("0.48")


def test_returns_none_when_all_quotes_are_stale():
    chain = make_chain()

    chain["callExpDateMap"]["2026-11-12:0"]["761.0"][0][
        "quoteTimeInLong"
    ] = timestamp_ms(
        NOW - timedelta(seconds=30)
    )

    contract = find_valid_fallback_contract(
        chain=chain,
        option_type="CALL",
        trading_date=TRADING_DATE,
        now=NOW,
    )

    assert contract is None


def test_returns_none_when_timestamp_is_missing():
    chain = make_chain()

    for contracts in chain["callExpDateMap"][
        "2026-11-12:0"
    ].values():
        for option in contracts:
            option.pop("quoteTimeInLong", None)

    contract = find_valid_fallback_contract(
        chain=chain,
        option_type="CALL",
        trading_date=TRADING_DATE,
        now=NOW,
    )

    assert contract is None


def test_explicit_strike_ignores_fallback_premium_range():
    chain = make_chain()

    # Casey explicitly requests the 762 CALL,
    # which costs $0.22.
    chain["callExpDateMap"]["2026-11-12:0"]["762.0"] = [
        {
            "symbol": "SPY 261112C00762000",
            "bid": 0.20,
            "ask": 0.22,
            "totalVolume": 100,
            "quoteTimeInLong": timestamp_ms(NOW),
        }
    ]

    contract = find_valid_explicit_contract(
        chain=chain,
        option_type="CALL",
        strike_price=Decimal("762"),
        trading_date=TRADING_DATE,
        now=NOW,
        stock_quote_response=make_valid_stock_quote(),
    )

    assert contract is not None
    assert contract.symbol == "SPY 261112C00762000"
    assert contract.ask == Decimal("0.22")


def test_explicit_strike_rejects_stale_quote():
    chain = make_chain()

    # The 760 CALL exists, but its quote is stale.
    contract = find_valid_explicit_contract(
        chain=chain,
        option_type="CALL",
        strike_price=Decimal("760"),
        trading_date=TRADING_DATE,
        now=NOW,
        stock_quote_response=make_valid_stock_quote(),
    )

    assert contract is None


def test_explicit_strike_never_substitutes_another_strike():
    chain = make_chain()

    # Casey requests 763 CALL, which isn't available.
    # The selector must NOT substitute 761 CALL.
    contract = find_valid_explicit_contract(
        chain=chain,
        option_type="CALL",
        strike_price=Decimal("763"),
        trading_date=TRADING_DATE,
        now=NOW,
        stock_quote_response=make_valid_stock_quote(),
    )

    assert contract is None


@pytest.mark.parametrize(
    "ask_price",
    ["0.19", "2.00"],
)
def test_explicit_selector_rejects_unsafe_premium(ask_price):
    chain = make_chain()

    option = chain["callExpDateMap"][
        "2026-11-12:0"
    ]["761.0"][0]

    option["ask"] = float(ask_price)
    option["bid"] = round(float(ask_price) * 0.95, 2)

    contract = find_valid_explicit_contract(
        chain=chain,
        option_type="CALL",
        strike_price=Decimal("761"),
        trading_date=TRADING_DATE,
        now=NOW,
        stock_quote_response=make_valid_stock_quote(),
    )

    assert contract is None


@pytest.mark.parametrize(
    "ask_price, expected_valid",
    [
        ("0.19", False),
        ("0.20", True),
        ("1.99", True),
        ("2.00", False),
    ],
)
def test_full_symbol_selector_enforces_premium_limits(
    ask_price,
    expected_valid,
):
    chain = make_chain()

    option = chain["callExpDateMap"][
        "2026-11-12:0"
    ]["761.0"][0]

    option["ask"] = float(ask_price)
    option["bid"] = round(float(ask_price) * 0.95, 2)

    # Include a fresh underlying quote so the
    # mandatory strike safety validation can pass.
    contract = find_valid_contract_by_symbol(
        chain=chain,
        contract_symbol="SPY 261112C00761000",
        trading_date=TRADING_DATE,
        now=NOW,
        stock_quote_response=make_valid_stock_quote(),
    )

    if expected_valid:
        assert contract is not None
        assert contract.symbol == "SPY 261112C00761000"
    else:
        assert contract is None


def test_fallback_selector_uses_configured_premium_range(
    monkeypatch,
):
    chain = make_chain()

    # Change the 761 CALL premium to $0.70.
    option = chain["callExpDateMap"][
        "2026-11-12:0"
    ]["761.0"][0]

    option["bid"] = 0.67
    option["ask"] = 0.70

    # Temporarily override settings for this test.
    monkeypatch.setattr(
        settings,
        "fallback_minimum_premium",
        Decimal("0.60"),
    )
    monkeypatch.setattr(
        settings,
        "fallback_maximum_premium",
        Decimal("0.80"),
    )

    contract = find_valid_fallback_contract(
        chain=chain,
        option_type="CALL",
        trading_date=TRADING_DATE,
        now=NOW,
    )

    assert contract is not None
    assert contract.symbol == "SPY 261112C00761000"
    assert contract.ask == Decimal("0.70")


def test_explicit_contract_requires_safe_strike():
    chain = make_chain()

    # SPY is trading around $650.
    # The 761 CALL is more than 2% away.
    stock_quote = {
        "SPY": {
            "quote": {
                "bidPrice": 649,
                "askPrice": 651,
                "quoteTime": timestamp_ms(NOW),
            }
        }
    }

    contract = find_valid_explicit_contract(
        chain=chain,
        option_type="CALL",
        strike_price=Decimal("761"),
        trading_date=TRADING_DATE,
        now=NOW,
        stock_quote_response=stock_quote,
    )

    assert contract is None


def test_explicit_contract_accepts_safe_strike():
    chain = make_chain()

    # SPY is trading around $760.
    stock_quote = make_valid_stock_quote()

    # Casey requests the 761 CALL.
    contract = find_valid_explicit_contract(
        chain=chain,
        option_type="CALL",
        strike_price=Decimal("761"),
        trading_date=TRADING_DATE,
        now=NOW,
        stock_quote_response=stock_quote,
    )

    assert contract is not None
    assert contract.symbol == "SPY 261112C00761000"
    assert contract.strike_price == Decimal("761")


def test_full_symbol_selector_rejects_unsafe_strike():
    chain = make_chain()

    # SPY is trading at approximately $650.
    # Casey's requested 761 CALL is too far away.
    stock_quote = {
        "SPY": {
            "quote": {
                "bidPrice": 649,
                "askPrice": 651,
                "quoteTime": timestamp_ms(NOW),
            }
        }
    }

    contract = find_valid_contract_by_symbol(
        chain=chain,
        contract_symbol="SPY 261112C00761000",
        trading_date=TRADING_DATE,
        now=NOW,
        stock_quote_response=stock_quote,
    )

    assert contract is None


def test_full_symbol_rejects_missing_stock_quote():
    """
    Reject an explicit contract when no underlying
    stock quote is provided.
    """
    contract = find_valid_contract_by_symbol(
        chain=make_chain(),
        contract_symbol="SPY 261112C00761000",
        trading_date=TRADING_DATE,
        now=NOW,
        stock_quote_response=None,
    )

    assert contract is None


def test_full_symbol_rejects_stale_stock_quote():
    """
    Reject an explicit contract when the underlying
    stock quote is older than 10 seconds.
    """
    stock_quote = make_valid_stock_quote()

    stock_quote["SPY"]["quote"]["quoteTime"] = timestamp_ms(
        NOW - timedelta(seconds=30)
    )

    contract = find_valid_contract_by_symbol(
        chain=make_chain(),
        contract_symbol="SPY 261112C00761000",
        trading_date=TRADING_DATE,
        now=NOW,
        stock_quote_response=stock_quote,
    )

    assert contract is None

"""Offline, fail-closed quote and chain parsing regression cases."""
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from my_trading_simulator.market_data.contract_selector import (
    OptionContract, find_contracts_by_premium, find_contract_by_strike, find_contract_by_symbol,
)
from my_trading_simulator.market_data.quote_validator import validate_option_quote

TODAY = date(2026, 11, 16)
NOW = datetime(2026, 11, 16, 15, tzinfo=timezone.utc)


def chain_with_quotes(options):
    return {
        "symbol": "SPY",
        "callExpDateMap": {"invalid-date": {"1": [{"symbol": "bad", "bid": 1, "ask": 1} ]},
            "2026-11-16:0": {"600": options}},
    }


def valid_option():
    return {"symbol": "SPY 261116C00600000", "bid": "0.43", "ask": "0.45", "totalVolume": 17,
            "quoteTimeInLong": int(NOW.timestamp() * 1000)}


@pytest.mark.parametrize("invalid", [
    {"bid": "NaN"}, {"ask": "Infinity"}, {"bid": True}, {"ask": "abc"},
    {"bid": "0.60"}, {"symbol": None}, {"totalVolume": "oops"},
    {"totalVolume": -3},
])
def test_invalid_chain_entries_are_skipped(invalid):
    bad = {**valid_option(), **invalid}
    chain = chain_with_quotes([bad, valid_option()])
    result = find_contracts_by_premium(chain, "CALL", expiration_date=TODAY)
    assert len(result) == 1
    assert result[0].symbol == valid_option()["symbol"]


def test_broken_chain_structure_rejected_without_crash():
    chain = {"symbol": "SPY", "callExpDateMap": {"2026-11-16:0": {"600": "not-list"}}}
    assert find_contracts_by_premium(chain, "CALL") == []
    assert find_contract_by_strike(chain, "CALL", Decimal("600"), TODAY) is None
    assert find_contract_by_symbol(chain, "SPY 261116C00600000", TODAY) is None


def test_exact_strike_and_symbol_skip_corrupt_quotes():
    bad = {**valid_option(), "ask": "NaN"}
    chain = chain_with_quotes([bad, valid_option()])
    assert find_contract_by_strike(chain, "CALL", Decimal("600"), TODAY).ask == Decimal("0.45")
    assert find_contract_by_symbol(chain, "SPY261116C00600000", TODAY).ask == Decimal("0.45")


@pytest.mark.parametrize("invalid", [Decimal("NaN"), Decimal("Infinity"), Decimal("-1"), Decimal("0")])
def test_invalid_quote_bid_rejected(invalid):
    contract = OptionContract(
        "SPY 261116C00600000", "SPY", "CALL", TODAY, Decimal("600"), invalid,
        Decimal("0.45"), 1,
    )
    valid, _ = validate_option_quote(contract, int(NOW.timestamp() * 1000), TODAY, now=NOW)
    assert not valid


@pytest.mark.parametrize("invalid", [Decimal("NaN"), Decimal("Infinity"), Decimal("-1"), Decimal("0")])
def test_invalid_quote_ask_rejected(invalid):
    contract = OptionContract(
        "SPY 261116C00600000", "SPY", "CALL", TODAY, Decimal("600"),
        Decimal("0.43"), invalid, 1,
    )
    valid, _ = validate_option_quote(contract, int(NOW.timestamp() * 1000), TODAY, now=NOW)
    assert not valid


def test_spread_rejects_zero_bid_explicitly():
    contract = OptionContract(
        "SPY 261116C00600000", "SPY", "CALL", TODAY, Decimal("600"),
        Decimal("0"), Decimal("0.45"), 1,
    )
    valid, reason = validate_option_quote(contract, int(NOW.timestamp() * 1000), TODAY, now=NOW)
    assert not valid
    assert reason == "Invalid bid price"


def test_reject_invalid_premium_range():
    with pytest.raises(ValueError, match="Invalid premium range"):
        find_contracts_by_premium(chain_with_quotes([valid_option()]), "CALL", target_min=Decimal("NaN"))

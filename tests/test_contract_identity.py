
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from my_trading_simulator.market_data.contract_selector import (
    OptionContract,
)
from my_trading_simulator.market_data.contract_identity import (
    validate_contract_identity,
)


TRADING_DATE = date(2026, 11, 12)


def make_contract():
    """
    Create a valid SPY 761 CALL contract.
    """
    return OptionContract(
        symbol="SPY 261112C00761000",
        underlying_symbol="SPY",
        option_type="CALL",
        expiration_date=TRADING_DATE,
        strike_price=Decimal("761"),
        bid=Decimal("0.44"),
        ask=Decimal("0.48"),
        volume=100,
    )


def validate(contract):
    return validate_contract_identity(
        contract=contract,
        expected_underlying="SPY",
        expected_option_type="CALL",
        expected_expiration=TRADING_DATE,
    )


def test_accepts_valid_contract():
    valid, reason = validate(make_contract())

    assert valid is True
    assert reason == "Contract identity is valid"


def test_rejects_wrong_symbol_underlying():
    contract = replace(
        make_contract(),
        symbol="QQQ 261112C00761000",
    )

    valid, reason = validate(contract)

    assert valid is False
    assert "underlying mismatch" in reason.lower()


def test_rejects_wrong_metadata_underlying():
    contract = replace(
        make_contract(),
        underlying_symbol="QQQ",
    )

    valid, _ = validate(contract)

    assert valid is False


def test_rejects_wrong_symbol_option_type():
    contract = replace(
        make_contract(),
        symbol="SPY 261112P00761000",
    )

    valid, _ = validate(contract)

    assert valid is False


def test_rejects_wrong_metadata_option_type():
    contract = replace(
        make_contract(),
        option_type="PUT",
    )

    valid, _ = validate(contract)

    assert valid is False


def test_rejects_wrong_symbol_expiration():
    contract = replace(
        make_contract(),
        symbol="SPY 261113C00761000",
    )

    valid, _ = validate(contract)

    assert valid is False


def test_rejects_wrong_metadata_expiration():
    contract = replace(
        make_contract(),
        expiration_date=date(2026, 11, 13),
    )

    valid, _ = validate(contract)

    assert valid is False


def test_rejects_wrong_symbol_strike():
    contract = replace(
        make_contract(),
        symbol="SPY 261112C00760000",
    )

    valid, _ = validate(contract)

    assert valid is False


def test_rejects_invalid_symbol_format():
    contract = replace(
        make_contract(),
        symbol="INVALID_OPTION_SYMBOL",
    )

    valid, _ = validate(contract)

    assert valid is False


@pytest.mark.parametrize(
    "symbol",
    [
        "SPY 261112C00761000",
        "SPY261112C00761000",
    ],
)
def test_symbol_format_handling(symbol):
    contract = replace(
        make_contract(),
        symbol=symbol,
    )

    valid, _ = validate(contract)

    # Current validator requires a space.
    assert valid is (symbol == "SPY 261112C00761000")


def test_rejects_missing_contract():
    valid = validate_contract_identity(
        contract=None,
        expected_underlying="SPY",
        expected_option_type="CALL",
        expected_expiration=TRADING_DATE,
    )

    assert valid[0] is False


def test_rejects_unsupported_underlying():
    valid, _ = validate_contract_identity(
        contract=make_contract(),
        expected_underlying="AAPL",
        expected_option_type="CALL",
        expected_expiration=TRADING_DATE,
    )

    assert valid is False

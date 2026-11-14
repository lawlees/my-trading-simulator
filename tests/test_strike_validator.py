
from decimal import Decimal

import pytest

from my_trading_simulator.market_data.strike_validator import (
    validate_strike_distance,
)


@pytest.mark.parametrize(
    "strike, underlying, expected",
    [
        ("760", "760", True),
        ("750", "760", True),
        ("745", "760", True),
        ("740", "760", False),
        ("660", "760", False),
        ("775", "760", True),
        ("780", "760", False),
    ],
)
def test_strike_distance_limits(
    strike,
    underlying,
    expected,
):
    valid, _ = validate_strike_distance(
        strike_price=Decimal(strike),
        underlying_price=Decimal(underlying),
    )

    assert valid is expected


@pytest.mark.parametrize(
    "strike, underlying",
    [
        ("0", "760"),
        ("-750", "760"),
        ("750", "0"),
        ("750", "-760"),
        ("NaN", "760"),
        ("Infinity", "760"),
        ("750", "NaN"),
        ("750", "Infinity"),
    ],
)
def test_rejects_invalid_prices(
    strike,
    underlying,
):
    valid, _ = validate_strike_distance(
        strike_price=Decimal(strike),
        underlying_price=Decimal(underlying),
    )

    assert valid is False


def test_custom_strike_distance_limit():
    valid, _ = validate_strike_distance(
        strike_price=Decimal("740"),
        underlying_price=Decimal("760"),
        max_distance_percent=Decimal("3.00"),
    )

    assert valid is True


def test_rejects_invalid_distance_limit():
    valid, _ = validate_strike_distance(
        strike_price=Decimal("750"),
        underlying_price=Decimal("760"),
        max_distance_percent=Decimal("0"),
    )

    assert valid is False


def test_exact_two_percent_boundary():
    valid, _ = validate_strike_distance(
        strike_price=Decimal("784.00"),
        underlying_price=Decimal("800.00"),
    )

    assert valid is True

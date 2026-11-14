
from decimal import Decimal

import pytest

from my_trading_simulator.market_data.premium_safety import (
    validate_contract_premium,
)


@pytest.mark.parametrize(
    "premium, expected",
    [
        ("0.10", False),
        ("0.19", False),
        ("0.20", True),
        ("0.40", True),
        ("0.50", True),
        ("1.50", True),
        ("1.99", True),
        ("2.00", False),
        ("2.50", False),
    ],
)
def test_explicit_contract_premium_limits(
    premium,
    expected,
):
    valid, _ = validate_contract_premium(
        ask=Decimal(premium),
        is_explicit=True,
    )

    assert valid is expected


@pytest.mark.parametrize(
    "premium, expected",
    [
        ("0.20", False),
        ("0.39", False),
        ("0.40", True),
        ("0.45", True),
        ("0.50", True),
        ("0.51", False),
        ("1.50", False),
    ],
)
def test_fallback_contract_premium_limits(
    premium,
    expected,
):
    valid, _ = validate_contract_premium(
        ask=Decimal(premium),
        is_explicit=False,
    )

    assert valid is expected


def test_rejects_zero_premium():
    valid, _ = validate_contract_premium(
        ask=Decimal("0"),
        is_explicit=True,
    )

    assert valid is False


def test_rejects_negative_premium():
    valid, _ = validate_contract_premium(
        ask=Decimal("-0.50"),
        is_explicit=True,
    )

    assert valid is False

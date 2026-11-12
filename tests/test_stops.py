
from decimal import Decimal

import pytest

from my_trading_simulator.strategy.stops import (
    calculate_break_even_stop,
)


@pytest.mark.parametrize(
    "entry_price, expected",
    [
        ("1.00", "1.02"),
        ("0.50", "0.52"),
        ("2.00", "2.02"),
        ("0.10", "0.12"),
    ],
)
def test_break_even_stop(entry_price, expected):
    result = calculate_break_even_stop(Decimal(entry_price))
    assert result == Decimal(expected)


def test_break_even_without_commission():
    result = calculate_break_even_stop(
        entry_price=Decimal("1.00"),
        commission_per_contract=Decimal("0"),
    )
    assert result == Decimal("1.00")


def test_break_even_with_custom_tick_size():
    result = calculate_break_even_stop(
        entry_price=Decimal("1.00"),
        tick_size=Decimal("0.05"),
    )
    assert result == Decimal("1.05")


@pytest.mark.parametrize(
    "entry_price",
    [
        Decimal("0"),
        Decimal("-1"),
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_invalid_entry_price(entry_price):
    with pytest.raises(ValueError):
        calculate_break_even_stop(entry_price)


from decimal import Decimal

import pytest

from my_trading_simulator.strategy.profit_taking import (
    calculate_profit_take_quantity,
)


@pytest.mark.parametrize(
    "original, remaining, expected",
    [
        (1, 1, 1),
        (2, 2, 1),
        (3, 3, 2),
        (4, 4, 3),
        (5, 5, 3),
        (8, 8, 6),
        (4, 2, 2),
        (4, 0, 0),
    ],
)
def test_profit_taking_quantities(original, remaining, expected):
    result = calculate_profit_take_quantity(original, remaining)
    assert result == expected


def test_custom_profit_fraction():
    result = calculate_profit_take_quantity(
        original_quantity=10,
        remaining_quantity=10,
        fraction=Decimal("0.50"),
    )

    assert result == 5


@pytest.mark.parametrize(
    "original, remaining",
    [
        (0, 0),
        (-1, 0),
        (4, -1),
        (4, 5),
    ],
)
def test_invalid_quantities(original, remaining):
    with pytest.raises(ValueError):
        calculate_profit_take_quantity(original, remaining)


@pytest.mark.parametrize(
    "fraction",
    [
        Decimal("0"),
        Decimal("-0.25"),
        Decimal("1.25"),
    ],
)
def test_invalid_fraction(fraction):
    with pytest.raises(ValueError):
        calculate_profit_take_quantity(4, 4, fraction)

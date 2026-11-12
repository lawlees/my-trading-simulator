
from decimal import Decimal, ROUND_CEILING


def calculate_break_even_stop(
    entry_price: Decimal,
    commission_per_contract: Decimal = Decimal("0.65"),
    contract_multiplier: int = 100,
    tick_size: Decimal = Decimal("0.01"),
) -> Decimal:
    """Calculate a fee-adjusted break-even option price."""

    if not isinstance(entry_price, Decimal) or not entry_price.is_finite():
        raise ValueError("Entry price must be a finite Decimal")

    if entry_price <= 0:
        raise ValueError("Entry price must be positive")

    if (
        not isinstance(commission_per_contract, Decimal)
        or not commission_per_contract.is_finite()
        or commission_per_contract < 0
    ):
        raise ValueError("Invalid commission")

    if type(contract_multiplier) is not int or contract_multiplier <= 0:
        raise ValueError("Invalid contract multiplier")

    if (
        not isinstance(tick_size, Decimal)
        or not tick_size.is_finite()
        or tick_size <= 0
    ):
        raise ValueError("Invalid tick size")

    total_commission = commission_per_contract * 2

    raw_break_even = (
        entry_price
        + total_commission / Decimal(contract_multiplier)
    )

    ticks = (
        raw_break_even / tick_size
    ).to_integral_value(rounding=ROUND_CEILING)

    return ticks * tick_size

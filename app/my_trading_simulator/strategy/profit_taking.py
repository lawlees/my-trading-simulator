from decimal import Decimal, ROUND_FLOOR


def calculate_profit_take_quantity(
    original_quantity: int,
    remaining_quantity: int,
    fraction: Decimal = Decimal("0.75"),
) -> int:
    """Calculate how many contracts to sell on the first profit-taking signal."""

    if original_quantity <= 0:
        raise ValueError("Original quantity must be positive")

    if remaining_quantity < 0 or remaining_quantity > original_quantity:
        raise ValueError("Invalid remaining quantity")

    if not Decimal("0") < fraction <= Decimal("1"):
        raise ValueError("Profit-taking fraction must be between 0 and 1")

    if remaining_quantity == 0:
        return 0

    target_quantity = int(
        (Decimal(original_quantity) * fraction).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )

    # For a single-contract position, close the entire position.
    if original_quantity == 1:
        target_quantity = 1

    # Never sell more than currently owned.
    return min(target_quantity, remaining_quantity)
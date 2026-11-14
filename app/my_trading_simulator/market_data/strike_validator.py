from decimal import Decimal, InvalidOperation

from my_trading_simulator.config.settings import settings


def validate_strike_distance(
    strike_price: Decimal,
    underlying_price: Decimal,
    max_distance_percent: Decimal | None = None,
) -> tuple[bool, str]:
    """
    Validate that an option strike is reasonably close
    to the underlying stock price.

    Returns:
        (True, reason) if valid.
        (False, reason) if invalid.
    """

    if max_distance_percent is None:
        max_distance_percent = (
            settings.max_strike_distance_percent
        )

    try:
        strike = Decimal(str(strike_price))
        underlying = Decimal(str(underlying_price))
        max_distance = Decimal(str(max_distance_percent))

        if not all(
            value.is_finite()
            for value in (
                strike,
                underlying,
                max_distance,
            )
        ):
            return False, "Non-finite strike validation input"

        if strike <= 0:
            return False, "Strike price must be positive"

        if underlying <= 0:
            return False, "Underlying price must be positive"

        if max_distance <= 0 or max_distance > 100:
            return False, "Invalid maximum strike distance"

        distance_percent = (
            abs(strike - underlying)
            / underlying
            * Decimal("100")
        )

    except (
        InvalidOperation,
        ValueError,
        TypeError,
        ZeroDivisionError,
    ):
        return False, "Invalid strike validation input"

    if distance_percent > max_distance:
        return (
            False,
            f"Strike is {distance_percent:.2f}% away "
            f"from underlying price, exceeding "
            f"{max_distance}% limit",
        )

    return True, "Strike distance within allowed limit"
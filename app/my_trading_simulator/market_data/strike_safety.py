
from datetime import datetime
from decimal import Decimal

from my_trading_simulator.market_data.stock_quote_validator import (
    validate_stock_quote,
)
from my_trading_simulator.market_data.strike_validator import (
    validate_strike_distance,
)


def validate_strike_with_stock_quote(
    strike_price: Decimal,
    symbol: str,
    stock_quote_response: dict,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """
    Validate an option strike against a fresh underlying
    stock quote.

    Returns:
        (True, reason) if both validations pass.
        (False, reason) if either validation fails.

    This function does not call Schwab or place orders.
    """

    underlying_price, quote_reason = validate_stock_quote(
        response=stock_quote_response,
        symbol=symbol,
        now=now,
    )

    if underlying_price is None:
        return False, quote_reason

    strike_valid, strike_reason = validate_strike_distance(
        strike_price=strike_price,
        underlying_price=underlying_price,
    )

    if not strike_valid:
        return False, strike_reason

    return True, "Strike and underlying quote are valid"

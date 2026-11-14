
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


def validate_stock_quote(
    response: dict,
    symbol: str,
    now: datetime | None = None,
    max_quote_age_seconds: int = 10,
) -> tuple[Decimal | None, str]:
    """
    Validate a Schwab stock/ETF quote.

    Returns:
        (midpoint, reason) when valid.
        (None, reason) when invalid.

    A valid quote requires:
    - Supported symbol
    - Positive, finite bid and ask
    - Bid <= ask
    - Valid quote timestamp
    - Quote age <= 10 seconds
    - Quote timestamp no more than 2 seconds in future
    """

    if not isinstance(symbol, str):
        return None, "Invalid underlying symbol"

    symbol = symbol.strip().upper()

    if symbol not in {"SPY", "QQQ", "IWM"}:
        return None, "Unsupported underlying symbol"

    if not isinstance(response, dict):
        return None, "Invalid Schwab response"

    stock_data = response.get(symbol)

    if not isinstance(stock_data, dict):
        return None, "Missing stock quote"

    quote = stock_data.get("quote")

    if not isinstance(quote, dict):
        return None, "Missing stock quote"

    try:
        bid = Decimal(str(quote["bidPrice"]))
        ask = Decimal(str(quote["askPrice"]))

        if not bid.is_finite() or not ask.is_finite():
            return None, "Non-finite stock price"

        if bid <= 0 or ask <= 0:
            return None, "Stock bid and ask must be positive"

        if bid > ask:
            return None, "Stock bid exceeds ask"

        timestamp_ms = quote["quoteTime"]

        if (
            isinstance(timestamp_ms, bool)
            or not isinstance(timestamp_ms, int)
            or timestamp_ms <= 0
        ):
            return None, "Invalid quote timestamp"

        if now is None:
            now = datetime.now(timezone.utc)

        if now.tzinfo is None:
            return None, "Current time must be timezone-aware"

        now_ms = int(now.timestamp() * 1000)

        quote_age_seconds = (
            now_ms - timestamp_ms
        ) / 1000

        if quote_age_seconds > max_quote_age_seconds:
            return None, "Stock quote is stale"

        if quote_age_seconds < -2:
            return None, "Stock quote timestamp is in the future"

        midpoint = (bid + ask) / Decimal("2")

        return midpoint, "Stock quote is valid"

    except (
        KeyError,
        TypeError,
        ValueError,
        InvalidOperation,
        OverflowError,
    ):
        return None, "Invalid stock quote data"

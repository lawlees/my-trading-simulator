"""Validate a Schwab exact-option quote against an existing paper position.

Read-only adapter. Does not execute paper fills, orders, or write to SQLite.
The SchwabMarketDataClient.get_option_quote() method must have already selected
and verified the exact requested top-level symbol key.
"""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from my_trading_simulator.market_data.contract_identity import (
    validate_contract_identity,
)
from my_trading_simulator.market_data.contract_selector import OptionContract
from my_trading_simulator.market_data.quote_validator import validate_option_quote


def validated_held_option_bid(
    position,
    response: dict,
    *,
    now: datetime | None = None,
) -> tuple[Decimal | None, str]:
    """Return (validated bid, reason), or (None, reason) on any unsafe quote.

    `response` is the one-symbol value returned by
    SchwabMarketDataClient.get_option_quote(position.option_symbol).
    This function intentionally fails closed on missing quote timestamps.
    It does NOT check exchange market hours; the monitor must do that.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None:
        return None, "Current time must be timezone-aware"
    if not isinstance(getattr(position, "option_symbol", None), str) or not position.option_symbol.strip():
        return None, "Position has no verified exact option symbol"
    if position.status != "OPEN" or position.remaining_quantity <= 0:
        return None, "Position is not open"
    if not isinstance(response, dict):
        return None, "Invalid Schwab option response"

    quote = response.get("quote")
    if not isinstance(quote, dict):
        return None, "Missing option quote"

    requested_symbol = position.option_symbol.strip().upper()
    # A contradictory symbol is a hard failure; an absent one is allowed
    # because the Schwab client already verified the response-map key.
    for raw_symbol in (response.get("symbol"), quote.get("symbol")):
        if raw_symbol is not None and (
            not isinstance(raw_symbol, str)
            or raw_symbol.strip().upper() != requested_symbol
        ):
            return None, "Schwab quote symbol mismatch"

    try:
        bid_raw, ask_raw = quote["bidPrice"], quote["askPrice"]
        if isinstance(bid_raw, bool) or isinstance(ask_raw, bool):
            return None, "Invalid option price"
        bid = Decimal(str(bid_raw))
        ask = Decimal(str(ask_raw))
        if not bid.is_finite() or not ask.is_finite():
            return None, "Non-finite option price"
        timestamp = quote["quoteTime"]
        if type(timestamp) is not int or timestamp <= 0:
            return None, "Missing or invalid quote timestamp"
        strike = Decimal(str(position.strike_price))
        if not strike.is_finite() or strike <= 0:
            return None, "Invalid position strike"
    except (KeyError, ValueError, TypeError, InvalidOperation):
        return None, "Invalid option quote fields"

    contract = OptionContract(
        symbol=requested_symbol,
        underlying_symbol=position.symbol,
        option_type=position.option_type,
        expiration_date=position.expiration_date,
        strike_price=strike,
        bid=bid,
        ask=ask,
        volume=0,
        quote_timestamp_ms=timestamp,
    )
    identity_ok, identity_reason = validate_contract_identity(
        contract,
        expected_underlying=position.symbol,
        expected_option_type=position.option_type,
        expected_expiration=position.expiration_date,
    )
    if not identity_ok:
        return None, identity_reason

    # 0DTE expiry is determined using the exchange-local date.
    trading_date = now.astimezone(ZoneInfo("America/New_York")).date()
    valid, reason = validate_option_quote(
        contract,
        quote_timestamp_ms=timestamp,
        trading_date=trading_date,
        now=now,
    )
    return (bid, "Quote valid") if valid else (None, reason)

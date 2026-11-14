
from datetime import date, datetime, timezone
from decimal import Decimal

from my_trading_simulator.market_data.contract_selector import (
    OptionContract,
)


def validate_option_quote(
    contract: OptionContract,
    quote_timestamp_ms: int,
    trading_date: date,
    now: datetime | None = None,
    max_age_seconds: int = 10,
    max_spread_fraction: Decimal = Decimal("0.20"),
) -> tuple[bool, str]:
    """
    Validate whether an option quote is suitable
    for simulated trading.

    Returns (is_valid, reason).
    """

    if now is None:
        now = datetime.now(timezone.utc)

    if now.tzinfo is None:
        return False, "Current time must be timezone-aware"

    if contract.expiration_date != trading_date:
        return False, "Contract is not 0DTE"

    if contract.bid < 0:
        return False, "Invalid bid price"

    if contract.ask <= 0:
        return False, "Invalid ask price"

    if contract.bid > contract.ask:
        return False, "Bid exceeds ask"

    spread = contract.ask - contract.bid
    spread_fraction = spread / contract.ask

    if spread_fraction > max_spread_fraction:
        return False, "Bid/ask spread too wide"


    # Reject missing values, strings, booleans,
    # negative timestamps, and zero.
    if (
        type(quote_timestamp_ms) is not int
        or quote_timestamp_ms <= 0
    ):
        return False, "Missing or invalid quote timestamp"

    # Extremely large timestamps may raise
    # OverflowError, OSError, or ValueError.
    try:
        quote_time = datetime.fromtimestamp(
            quote_timestamp_ms / 1000,
            tz=timezone.utc,
        )
    except (OverflowError, OSError, ValueError):
        return False, "Missing or invalid quote timestamp"


    age_seconds = (now - quote_time).total_seconds()

    if age_seconds < -2:
        return False, "Quote timestamp is in the future"

    if age_seconds > max_age_seconds:
        return False, "Quote is stale"

    return True, "Quote is valid"



def validate_contract_for_paper_trade(
    contract: OptionContract,
    trading_date: date,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """
    Validate a Schwab option contract before
    considering it for a simulated trade.

    Uses the actual quote timestamp stored
    in OptionContract.
    """

    return validate_option_quote(
        contract=contract,
        quote_timestamp_ms=contract.quote_timestamp_ms,
        trading_date=trading_date,
        now=now,
    )

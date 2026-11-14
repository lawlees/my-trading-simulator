
from decimal import Decimal

from my_trading_simulator.config.settings import settings


def validate_contract_premium(
    ask: Decimal,
    is_explicit: bool,
    minimum_premium: Decimal | None = None,
    maximum_premium: Decimal | None = None,
    fallback_minimum: Decimal | None = None,
    fallback_maximum: Decimal | None = None,
) -> tuple[bool, str]:
    """
    Validate option premiums using centralized settings.

    Explicit contracts:
        minimum <= ask < maximum

    Fallback contracts:
        fallback_minimum <= ask <= fallback_maximum

    Optional parameters allow overriding individual
    limits in tests without changing global settings.
    """

    if minimum_premium is None:
        minimum_premium = settings.minimum_option_premium

    if maximum_premium is None:
        maximum_premium = settings.maximum_option_premium

    if fallback_minimum is None:
        fallback_minimum = settings.fallback_minimum_premium

    if fallback_maximum is None:
        fallback_maximum = settings.fallback_maximum_premium

    if not isinstance(ask, Decimal):
        return False, "Invalid option premium"

    if not ask.is_finite() or ask <= 0:
        return False, "Invalid option premium"

    if minimum_premium <= 0:
        raise ValueError(
            "Minimum premium must be positive"
        )

    if maximum_premium <= minimum_premium:
        raise ValueError(
            "Maximum premium must exceed minimum"
        )

    if fallback_minimum > fallback_maximum:
        raise ValueError(
            "Invalid fallback premium range"
        )

    # Universal premium safety limits
    if ask < minimum_premium:
        return False, "Option premium below safety minimum"

    if ask >= maximum_premium:
        return False, "Option premium exceeds safety maximum"

    # Casey's explicit contract may be outside
    # the fallback range, but not safety limits.
    if is_explicit:
        return True, "Explicit contract premium accepted"

    # Automatically selected contracts must
    # remain inside the fallback range.
    if not fallback_minimum <= ask <= fallback_maximum:
        return False, "Outside fallback premium range"

    return True, "Fallback contract premium accepted"

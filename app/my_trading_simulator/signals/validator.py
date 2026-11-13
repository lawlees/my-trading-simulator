
from my_trading_simulator.signals.models import (
    SignalAction,
    TradingSignal,
)


SUPPORTED_SYMBOLS = {"SPY", "QQQ", "IWM"}


def validate_signal(signal: TradingSignal) -> TradingSignal:
    """
    Apply deterministic safety rules to an LLM-generated signal.

    This validates classification completeness only.
    It does not authorize trade execution.
    """

    # Work on a copy so the original LLM output remains unchanged.
    validated = signal.model_copy(deep=True)

    # Normalize the symbol.
    if validated.symbol is not None:
        validated.symbol = validated.symbol.strip().upper()

    # IGNORE must never be actionable.
    if validated.action == SignalAction.IGNORE:
        validated.is_actionable = False
        return validated

    # Reject unsupported or missing symbols.
    if validated.symbol not in SUPPORTED_SYMBOLS:
        validated.is_actionable = False
        validated.reason = (
            f"{validated.reason} "
            "Validation: missing or unsupported symbol."
        )
        return validated

    # BUY requires a CALL or PUT direction.
    if validated.action == SignalAction.BUY:
        if validated.option_type is None:
            validated.is_actionable = False
            validated.reason = (
                f"{validated.reason} "
                "Validation: BUY requires an option type."
            )
            return validated

    # The LLM's intent must also be marked actionable.
    if not validated.is_actionable:
        return validated

    return validated

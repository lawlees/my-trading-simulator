"""Deterministic validation of classified Discord signals.

A valid classification is NOT authorization to place a paper trade.
"""

from my_trading_simulator.signals.models import SignalAction, TradingSignal

SUPPORTED_SYMBOLS = frozenset({"SPY", "QQQ", "IWM"})


def validate_signal(signal: TradingSignal) -> TradingSignal:
    """Return a validated COPY of a TradingSignal, failing closed on ambiguity."""
    result = signal.model_copy(deep=True)

    if result.symbol is not None:
        result.symbol = result.symbol.strip().upper()
        if result.symbol not in SUPPORTED_SYMBOLS:
            result.is_actionable = False
            result.reason = "Unsupported underlying symbol"
            return result

    if result.action == SignalAction.IGNORE:
        result.is_actionable = False
        return result

    if result.action == SignalAction.BUY:
        if result.symbol is None or result.option_type is None:
            result.is_actionable = False
            result.reason = "BUY requires a supported symbol and CALL/PUT"

    elif result.action == SignalAction.ADD:
        # ADD must also be checked against persisted trade-idea context.
        result.is_actionable = False
        result.reason = "ADD requires contextual and broker-level validation"

    elif result.action in (SignalAction.CLOSE, SignalAction.PROFIT_TAKE):
        if result.symbol is None:
            result.is_actionable = False
            result.reason = "Exit requires an unambiguous open-position symbol"

    else:
        result.is_actionable = False
        result.reason = "Unsupported signal action"

    return result

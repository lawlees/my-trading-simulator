"""Deterministic validation of classified Discord signals.

A valid classification is NOT authorization to place a paper trade.
"""

import re

from my_trading_simulator.signals.models import SignalAction, TradingSignal

SUPPORTED_SYMBOLS = frozenset({"SPY", "QQQ", "IWM"})


def explicit_contract_error(signal: TradingSignal) -> str | None:
    """Return a fail-closed error for incompatible explicit instructions."""
    if signal.strike_price is not None and signal.contract_symbol is not None:
        return "Conflicting explicit contract instructions"
    if signal.contract_symbol is not None:
        match = re.fullmatch(
            r"(SPY|QQQ|IWM) (\d{6})([CP])(\d{8})",
            signal.contract_symbol,
        )
        if not match or signal.symbol != match.group(1):
            return "Option contract symbol does not match underlying"
        expected = "CALL" if match.group(3) == "C" else "PUT"
        if signal.option_type is None or signal.option_type.value != expected:
            return "Option contract type does not match signal"
    if signal.action not in (SignalAction.BUY, SignalAction.ADD) and (
        signal.strike_price is not None or signal.contract_symbol is not None
    ):
        return "Explicit contract instructions require BUY or ADD"
    return None


def validate_signal(signal: TradingSignal) -> TradingSignal:
    """Return a validated COPY of a TradingSignal, failing closed on ambiguity."""
    result = signal.model_copy(deep=True)

    if result.symbol is not None:
        result.symbol = result.symbol.strip().upper()
        if result.symbol not in SUPPORTED_SYMBOLS:
            result.is_actionable = False
            result.reason = "Unsupported underlying symbol"
            return result

    contract_error = explicit_contract_error(result)
    if contract_error is not None:
        result.is_actionable = False
        result.reason = contract_error
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

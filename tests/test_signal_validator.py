
import pytest

from my_trading_simulator.signals.models import (
    SignalAction,
    TradingSignal,
)
from my_trading_simulator.signals.validator import validate_signal


def make_signal(
    action=SignalAction.BUY,
    symbol="SPY",
    option_type="CALL",
    is_actionable=True,
):
    return TradingSignal(
        message_id="test-001",
        raw_message="Test trading message",
        action=action,
        symbol=symbol,
        option_type=option_type,
        is_actionable=is_actionable,
        reason="Test classification",
    )


def test_valid_buy():
    signal = validate_signal(make_signal())

    assert signal.action == SignalAction.BUY
    assert signal.symbol == "SPY"
    assert signal.is_actionable is True


def test_buy_missing_option_type():
    signal = validate_signal(
        make_signal(option_type=None)
    )

    assert signal.is_actionable is False


def test_unsupported_symbol():
    signal = validate_signal(
        make_signal(symbol="TSLA")
    )

    assert signal.is_actionable is False


def test_missing_symbol():
    signal = validate_signal(
        make_signal(symbol=None)
    )

    assert signal.is_actionable is False


def test_ignore_cannot_be_actionable():
    signal = validate_signal(
        make_signal(
            action=SignalAction.IGNORE,
            is_actionable=True,
        )
    )

    assert signal.is_actionable is False


def test_close_without_symbol():
    signal = validate_signal(
        make_signal(
            action=SignalAction.CLOSE,
            symbol=None,
            option_type=None,
        )
    )

    assert signal.is_actionable is False


def test_profit_take_without_option_type():
    signal = validate_signal(
        make_signal(
            action=SignalAction.PROFIT_TAKE,
            symbol="QQQ",
            option_type=None,
        )
    )

    assert signal.is_actionable is True


def test_symbol_normalization():
    signal = validate_signal(
        make_signal(symbol=" spy ")
    )

    assert signal.symbol == "SPY"
    assert signal.is_actionable is True


def test_validation_does_not_modify_original():
    original = make_signal(symbol=" spy ")

    validated = validate_signal(original)

    assert original.symbol == " spy "
    assert validated.symbol == "SPY"

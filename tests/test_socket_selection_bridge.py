"""Safe contract selection must default to the isolated socket."""

from decimal import Decimal
from datetime import date

from my_trading_simulator.market_data import market_data_coordinator as module
from my_trading_simulator.market_data.socket_client import MarketDataSocketClient
from my_trading_simulator.signals.models import TradingSignal, SignalAction, OptionType
from my_trading_simulator.signals.validator import validate_signal
from my_trading_simulator.signals.add_validator import validate_add_signal


def signal(**updates):
    details = dict(message_id="discord-test", raw_message="Taking SPY calls",
                   action=SignalAction.BUY, symbol="SPY", option_type=OptionType.CALL,
                   is_actionable=True, reason="explicit entry")
    details.update(updates)
    return TradingSignal(**details)


def test_coordinator_uses_socket_by_default():
    coordinator = module.MarketDataCoordinator()
    assert isinstance(coordinator.client, MarketDataSocketClient)


def test_explicit_strike_preserved():
    original = signal(strike_price=Decimal("761"))
    checked = validate_signal(original)
    assert checked.is_actionable is True
    assert checked.strike_price == Decimal("761")
    assert original is not checked


def test_conflicting_contract_instructions_rejected():
    checked = validate_signal(signal(strike_price=Decimal("761"),
                                     contract_symbol="SPY 261116C00761000"))
    assert checked.is_actionable is False
    assert "Conflicting" in checked.reason


def test_contract_direction_mismatch_rejected():
    checked = validate_signal(signal(contract_symbol="SPY 261116P00761000"))
    assert checked.is_actionable is False


def test_contract_underlying_mismatch_rejected():
    checked = validate_signal(signal(contract_symbol="QQQ 261116C00761000"))
    assert checked.is_actionable is False


def test_valid_explicit_contract_preserved():
    checked = validate_signal(signal(contract_symbol="SPY 261116C00761000"))
    assert checked.is_actionable is True
    assert checked.contract_symbol == "SPY 261116C00761000"


def test_close_with_explicit_contract_rejected():
    checked = validate_signal(signal(action=SignalAction.CLOSE,
                                     contract_symbol="SPY 261116C00761000"))
    assert checked.is_actionable is False


def test_negative_strike_fails_model_validation():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        signal(strike_price=Decimal("-1"))


def test_option_symbol_cannot_be_guessed_from_malformed_string():
    checked = validate_signal(signal(contract_symbol="SPY 261116C00761000 extra"))
    assert checked.is_actionable is False


def test_add_without_context_not_authorized_even_with_strike():
    checked = validate_add_signal(signal(action=SignalAction.ADD,
                                          strike_price=Decimal("761")), None)
    assert checked.is_actionable is False

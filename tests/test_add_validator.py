from decimal import Decimal
from my_trading_simulator.signals.context import PositionContext
import pytest

from my_trading_simulator.signals.add_validator import (
    validate_add_signal,
)
from my_trading_simulator.signals.models import (
    OptionType,
    SignalAction,
    TradingSignal,
)
from my_trading_simulator.signals.snapshot import (
    TradingContextSnapshot,
)
from my_trading_simulator.signals.trade_context import (
    TradeIdeaContext,
)


def make_context(
    symbol="SPY",
    option_type="CALL",
    additions_used=0,
    valid=True,
    has_idea=True,
):
    idea = None

    if has_idea:
        idea = TradeIdeaContext(
            trade_idea_id=42,
            symbol=symbol,
            option_type=option_type,
            size_type="NORMAL",
            initial_allocation=Decimal("400"),
            initial_risk_limit=Decimal("150"),
            additions_used=additions_used,
            status="ACTIVE",
        )

    return TradingContextSnapshot(
        active_position=None,
        active_trade_idea=idea,
        recent_messages=[],
        open_position_count=0 if valid else 2,
        active_trade_idea_count=1 if has_idea else 0,
        context_is_valid=valid,
    )


def make_add_signal(
    symbol=None,
    option_type=None,
    actionable=True,
):
    return TradingSignal(
        message_id="test-add-1",
        raw_message="Adding here",
        action=SignalAction.ADD,
        symbol=symbol,
        option_type=option_type,
        is_actionable=actionable,
        reason="Casey explicitly added",
    )


def test_add_matches_existing_trade_idea():
    signal = make_add_signal(
        symbol="SPY",
        option_type=OptionType.CALL,
    )

    result = validate_add_signal(
        signal,
        make_context(),
    )

    assert result.is_actionable is True
    assert result.symbol == "SPY"
    assert result.option_type == OptionType.CALL


def test_add_resolves_missing_symbol_and_option_type():
    signal = make_add_signal()

    result = validate_add_signal(
        signal,
        make_context(),
    )

    assert result.symbol == "SPY"
    assert result.option_type == OptionType.CALL
    assert result.is_actionable is True


def test_add_without_active_idea_is_blocked():
    result = validate_add_signal(
        make_add_signal(),
        make_context(has_idea=False),
    )

    assert result.is_actionable is False
    assert "active trade idea" in result.reason


def test_second_add_is_blocked():
    result = validate_add_signal(
        make_add_signal(),
        make_context(additions_used=1),
    )

    assert result.is_actionable is False
    assert "limit" in result.reason


def test_add_with_wrong_symbol_is_blocked():
    result = validate_add_signal(
        make_add_signal(
            symbol="QQQ",
            option_type=OptionType.PUT,
        ),
        make_context(),
    )

    assert result.is_actionable is False
    assert "symbol" in result.reason


def test_add_with_wrong_option_type_is_blocked():
    result = validate_add_signal(
        make_add_signal(
            symbol="SPY",
            option_type=OptionType.PUT,
        ),
        make_context(),
    )

    assert result.is_actionable is False
    assert "option type" in result.reason


def test_add_without_context_is_blocked():
    result = validate_add_signal(
        make_add_signal(),
        None,
    )

    assert result.is_actionable is False
    assert "requires trading context" in result.reason


def test_invalid_context_blocks_add():
    result = validate_add_signal(
        make_add_signal(),
        make_context(valid=False),
    )

    assert result.is_actionable is False
    assert "invalid trading context" in result.reason


def test_validator_does_not_authorize_blocked_signal():
    result = validate_add_signal(
        make_add_signal(actionable=False),
        make_context(),
    )

    assert result.is_actionable is False


def test_validator_does_not_modify_original():
    signal = make_add_signal()

    validate_add_signal(signal, make_context())

    assert signal.symbol is None
    assert signal.option_type is None


def test_non_add_signal_is_unchanged():
    signal = TradingSignal(
        message_id="test-buy-1",
        raw_message="Taking SPY calls",
        action=SignalAction.BUY,
        symbol="SPY",
        option_type=OptionType.CALL,
        is_actionable=True,
        reason="Explicit entry",
    )

    result = validate_add_signal(signal, None)

    assert result.action == SignalAction.BUY
    assert result.is_actionable is True



def make_context_with_position(
    profit_take_completed=False,
    profit_take_status="PENDING",
):
    context = make_context()

    position = PositionContext(
        position_id=100,
        symbol="SPY",
        option_type="CALL",
        remaining_quantity=4,
        profit_take_completed=profit_take_completed,
        profit_take_status=profit_take_status,
    )

    return TradingContextSnapshot(
        active_position=position,
        active_trade_idea=context.active_trade_idea,
        recent_messages=[],
        open_position_count=1,
        active_trade_idea_count=1,
        context_is_valid=True,
    )



def test_add_before_profit_taking_is_eligible():
    result = validate_add_signal(
        make_add_signal(),
        make_context_with_position(
            profit_take_completed=False,
        ),
    )

    assert result.is_actionable is True
    assert result.symbol == "SPY"
    assert result.option_type == OptionType.CALL


def test_add_after_profit_taking_is_blocked():
    result = validate_add_signal(
        make_add_signal(),
        make_context_with_position(
            profit_take_completed=True,
        ),
    )

    assert result.is_actionable is False
    assert "partial profit-taking" in result.reason


def test_add_after_stop_out_remains_eligible():
    result = validate_add_signal(
        make_add_signal(),
        make_context(
            has_idea=True,
            additions_used=0,
        ),
    )

    assert result.is_actionable is True
    assert result.symbol == "SPY"
    assert result.option_type == OptionType.CALL

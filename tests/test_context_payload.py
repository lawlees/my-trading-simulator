
import json
from datetime import datetime, timezone
from decimal import Decimal

from my_trading_simulator.signals.context import PositionContext
from my_trading_simulator.signals.history import MessageContext
from my_trading_simulator.signals.trade_context import TradeIdeaContext
from my_trading_simulator.signals.snapshot import TradingContextSnapshot
from my_trading_simulator.signals.context_payload import build_context_payload


def test_empty_context_payload():
    snapshot = TradingContextSnapshot(
        active_position=None,
        active_trade_idea=None,
        recent_messages=[],
        open_position_count=0,
        active_trade_idea_count=0,
        context_is_valid=True,
    )

    payload = json.loads(build_context_payload(snapshot))

    assert payload["context_is_valid"] is True
    assert payload["open_position_count"] == 0
    assert payload["active_position"] is None
    assert payload["active_trade_idea"] is None
    assert payload["recent_messages"] == []


def test_trade_idea_and_history_payload():
    idea = TradeIdeaContext(
        trade_idea_id=42,
        symbol="SPY",
        option_type="CALL",
        size_type="NORMAL",
        initial_allocation=Decimal("400"),
        initial_risk_limit=Decimal("150"),
        additions_used=0,
        status="ACTIVE",
    )

    message = MessageContext(
        discord_message_id="12345",
        message_text="Taking SPY calls here",
        message_timestamp=datetime(
            2026, 11, 12, 15, 0, tzinfo=timezone.utc
        ),
        action="BUY",
        trade_idea_id=42,
        position_id=None,
    )

    snapshot = TradingContextSnapshot(
        active_position=None,
        active_trade_idea=idea,
        recent_messages=[message],
        open_position_count=0,
        active_trade_idea_count=1,
        context_is_valid=True,
    )

    payload = json.loads(build_context_payload(snapshot))

    assert payload["active_trade_idea"]["trade_idea_id"] == 42
    assert payload["active_trade_idea"]["initial_allocation"] == "400"
    assert payload["active_trade_idea"]["additions_used"] == 0

    assert payload["recent_messages"][0]["message_text"] == (
        "Taking SPY calls here"
    )
    assert payload["recent_messages"][0]["message_timestamp"] == (
        "2026-11-12T15:00:00+00:00"
    )


def test_invalid_context_is_preserved():
    snapshot = TradingContextSnapshot(
        active_position=None,
        active_trade_idea=None,
        recent_messages=[],
        open_position_count=2,
        active_trade_idea_count=1,
        context_is_valid=False,
    )

    payload = json.loads(build_context_payload(snapshot))

    assert payload["context_is_valid"] is False
    assert payload["open_position_count"] == 2


def test_decimal_serialization_preserves_precision():
    idea = TradeIdeaContext(
        trade_idea_id=7,
        symbol="QQQ",
        option_type="PUT",
        size_type="LIGHT",
        initial_allocation=Decimal("200.00"),
        initial_risk_limit=Decimal("75.00"),
        additions_used=1,
        status="ACTIVE",
    )

    snapshot = TradingContextSnapshot(
        active_position=None,
        active_trade_idea=idea,
        recent_messages=[],
        open_position_count=0,
        active_trade_idea_count=1,
        context_is_valid=True,
    )

    payload = json.loads(build_context_payload(snapshot))

    assert payload["active_trade_idea"]["initial_allocation"] == "200.00"
    assert payload["active_trade_idea"]["initial_risk_limit"] == "75.00"
    assert payload["active_trade_idea"]["additions_used"] == 1

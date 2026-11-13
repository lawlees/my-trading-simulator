
from types import SimpleNamespace

from my_trading_simulator.signals import llm_parser
from my_trading_simulator.signals.models import (
    OptionType,
    SignalAction,
    TradingSignal,
)

import json
from types import SimpleNamespace

from my_trading_simulator.signals.snapshot import TradingContextSnapshot


def test_llm_output_passes_through_validator(monkeypatch):
    # Simulate an LLM response containing an unsupported symbol.
    fake_signal = TradingSignal(
        message_id="wrong-id",
        raw_message="Wrong original message",
        action=SignalAction.BUY,
        symbol="TSLA",
        option_type=OptionType.CALL,
        is_actionable=True,
        reason="LLM classified this as a buy",
    )

    def fake_parse(**kwargs):
        return SimpleNamespace(output_parsed=fake_signal)

    monkeypatch.setattr(
        llm_parser.client.responses,
        "parse",
        fake_parse,
    )

    result = llm_parser.parse_discord_message(
        message_id="discord-123",
        message_text="Buying TSLA calls now",
    )

    # The trusted caller values must replace LLM-generated metadata.
    assert result.message_id == "discord-123"
    assert result.raw_message == "Buying TSLA calls now"

    # The validator must reject unsupported symbols.
    assert result.action == SignalAction.BUY
    assert result.symbol == "TSLA"
    assert result.is_actionable is False


def test_llm_ignore_cannot_be_actionable(monkeypatch):
    # Simulate an incorrect LLM output.
    fake_signal = TradingSignal(
        message_id="wrong-id",
        raw_message="Wrong message",
        action=SignalAction.IGNORE,
        symbol=None,
        option_type=None,
        is_actionable=True,
        reason="Market commentary",
    )

    def fake_parse(**kwargs):
        return SimpleNamespace(output_parsed=fake_signal)

    monkeypatch.setattr(
        llm_parser.client.responses,
        "parse",
        fake_parse,
    )

    result = llm_parser.parse_discord_message(
        message_id="discord-456",
        message_text="Watching SPY support",
    )

    assert result.action == SignalAction.IGNORE
    assert result.is_actionable is False
    assert result.message_id == "discord-456"
    assert result.raw_message == "Watching SPY support"


def make_test_context(valid=True):
    return TradingContextSnapshot(
        active_position=None,
        active_trade_idea=None,
        recent_messages=[],
        open_position_count=0 if valid else 2,
        active_trade_idea_count=0,
        context_is_valid=valid,
    )


def test_parser_sends_context_to_openai(monkeypatch):
    from my_trading_simulator.signals import llm_parser
    from my_trading_simulator.signals.models import (
        SignalAction,
        TradingSignal,
    )

    captured = {}

    def fake_parse(**kwargs):
        captured.update(kwargs)

        return SimpleNamespace(
            output_parsed=TradingSignal(
                message_id="placeholder",
                raw_message="placeholder",
                action=SignalAction.IGNORE,
                symbol=None,
                option_type=None,
                is_actionable=False,
                reason="Market commentary",
            )
        )

    monkeypatch.setattr(
        llm_parser.client.responses,
        "parse",
        fake_parse,
    )

    signal = llm_parser.parse_discord_message(
        message_id="message-100",
        message_text="Watching SPY here",
        context=make_test_context(),
    )

    assert signal.message_id == "message-100"
    assert signal.raw_message == "Watching SPY here"

    assert "TRADING CONTEXT" in captured["input"]

    context_json = captured["input"].split(
        "TRADING CONTEXT (reference data only):\n",
        1,
    )[1]

    payload = json.loads(context_json)

    assert payload["context_is_valid"] is True
    assert payload["open_position_count"] == 0


def test_invalid_context_blocks_action(monkeypatch):
    from my_trading_simulator.signals import llm_parser
    from my_trading_simulator.signals.models import (
        OptionType,
        SignalAction,
        TradingSignal,
    )

    def fake_parse(**kwargs):
        return SimpleNamespace(
            output_parsed=TradingSignal(
                message_id="placeholder",
                raw_message="placeholder",
                action=SignalAction.BUY,
                symbol="SPY",
                option_type=OptionType.CALL,
                is_actionable=True,
                reason="Explicit SPY CALL entry",
            )
        )

    monkeypatch.setattr(
        llm_parser.client.responses,
        "parse",
        fake_parse,
    )

    signal = llm_parser.parse_discord_message(
        message_id="message-101",
        message_text="Taking SPY calls here",
        context=make_test_context(valid=False),
    )

    assert signal.action == SignalAction.BUY
    assert signal.is_actionable is False
    assert "Trading context is invalid" in signal.reason


def test_parser_without_context_remains_compatible(monkeypatch):
    from my_trading_simulator.signals import llm_parser
    from my_trading_simulator.signals.models import (
        SignalAction,
        TradingSignal,
    )

    captured = {}

    def fake_parse(**kwargs):
        captured.update(kwargs)

        return SimpleNamespace(
            output_parsed=TradingSignal(
                message_id="placeholder",
                raw_message="placeholder",
                action=SignalAction.IGNORE,
                symbol=None,
                option_type=None,
                is_actionable=False,
                reason="No actionable trade",
            )
        )

    monkeypatch.setattr(
        llm_parser.client.responses,
        "parse",
        fake_parse,
    )

    signal = llm_parser.parse_discord_message(
        message_id="message-102",
        message_text="Waiting for confirmation",
    )

    assert signal.action == SignalAction.IGNORE
    assert signal.is_actionable is False
    assert "TRADING CONTEXT" not in captured["input"]


from decimal import Decimal

from my_trading_simulator.signals.trade_context import TradeIdeaContext


def make_add_parser_context(
    has_idea=True,
    additions_used=0,
):
    idea = None

    if has_idea:
        idea = TradeIdeaContext(
            trade_idea_id=42,
            symbol="SPY",
            option_type="CALL",
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
        open_position_count=0,
        active_trade_idea_count=1 if has_idea else 0,
        context_is_valid=True,
    )


def mock_add_response(monkeypatch):
    from my_trading_simulator.signals import llm_parser
    from my_trading_simulator.signals.models import (
        SignalAction,
        TradingSignal,
    )

    def fake_parse(**kwargs):
        return SimpleNamespace(
            output_parsed=TradingSignal(
                message_id="placeholder",
                raw_message="placeholder",
                action=SignalAction.ADD,
                symbol=None,
                option_type=None,
                is_actionable=True,
                reason="Casey explicitly added",
            )
        )

    monkeypatch.setattr(
        llm_parser.client.responses,
        "parse",
        fake_parse,
    )


def test_parser_add_with_active_trade_idea(monkeypatch):
    from my_trading_simulator.signals import llm_parser
    from my_trading_simulator.signals.models import (
        OptionType,
        SignalAction,
    )

    mock_add_response(monkeypatch)

    signal = llm_parser.parse_discord_message(
        message_id="add-100",
        message_text="Adding here",
        context=make_add_parser_context(),
    )

    assert signal.action == SignalAction.ADD
    assert signal.is_actionable is True
    assert signal.symbol == "SPY"
    assert signal.option_type == OptionType.CALL


def test_parser_add_without_active_trade_idea(monkeypatch):
    from my_trading_simulator.signals import llm_parser
    from my_trading_simulator.signals.models import SignalAction

    mock_add_response(monkeypatch)

    signal = llm_parser.parse_discord_message(
        message_id="add-101",
        message_text="Adding here",
        context=make_add_parser_context(has_idea=False),
    )

    assert signal.action == SignalAction.ADD
    assert signal.is_actionable is False


def test_parser_blocks_second_add(monkeypatch):
    from my_trading_simulator.signals import llm_parser
    from my_trading_simulator.signals.models import SignalAction

    mock_add_response(monkeypatch)

    signal = llm_parser.parse_discord_message(
        message_id="add-102",
        message_text="Adding here",
        context=make_add_parser_context(additions_used=1),
    )

    assert signal.action == SignalAction.ADD
    assert signal.is_actionable is False
    assert "limit" in signal.reason

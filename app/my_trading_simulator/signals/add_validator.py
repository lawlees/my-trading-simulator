
from my_trading_simulator.signals.models import (
    SignalAction,
    TradingSignal,
)
from my_trading_simulator.signals.snapshot import (
    TradingContextSnapshot,
)
from my_trading_simulator.signals.context import PositionContext

def validate_add_signal(
    signal: TradingSignal,
    context: TradingContextSnapshot | None,
    max_additions: int = 1,
) -> TradingSignal:
    """
    Validate ADD eligibility using trading context.

    This is a preliminary signal check only.
    The execution layer must recheck all rules
    atomically before placing a simulated order.
    """
    validated = signal.model_copy(deep=True)

    if validated.action != SignalAction.ADD:
        return validated

    def block(reason: str) -> TradingSignal:
        validated.is_actionable = False
        validated.reason = reason
        return validated

    if context is None:
        return block("ADD requires trading context")

    if not context.context_is_valid:
        return block("ADD blocked: invalid trading context")

    idea = context.active_trade_idea

    if idea is None:
        return block("ADD requires an active trade idea")

    if idea.additions_used >= max_additions:
        return block("ADD limit already reached")

    if idea.status != "ACTIVE":
        return block("ADD requires an ACTIVE trade idea")

    if (
        validated.symbol is not None
        and validated.symbol.upper() != idea.symbol
    ):
        return block("ADD symbol does not match active trade idea")

    if (
        validated.option_type is not None
        and validated.option_type.value != idea.option_type
    ):
        return block("ADD option type does not match active trade idea")


    if context.active_position is not None:
        position = context.active_position

        if position.symbol != idea.symbol:
            return block(
                "Open position does not match ADD trade idea"
            )

        if position.option_type != idea.option_type:
            return block(
                "Open position option type does not match ADD"
            )

        if (
            position.profit_take_completed
            or position.profit_take_status != "PENDING"
        ):
            return block(
                "ADD blocked: partial profit-taking "
                "has started or completed"
            )


    # Resolve omitted details from the active trade idea.
    validated.symbol = idea.symbol
    validated.option_type = idea.option_type

    # Passing this check is not execution authorization.
    return validated


def make_context_with_position(
    profit_take_completed=False,
):
    context = make_context()

    position = PositionContext(
        position_id=100,
        symbol="SPY",
        option_type="CALL",
        remaining_quantity=4,
        profit_take_completed=profit_take_completed,
    )

    return TradingContextSnapshot(
        active_position=position,
        active_trade_idea=context.active_trade_idea,
        recent_messages=[],
        open_position_count=1,
        active_trade_idea_count=1,
        context_is_valid=True,
    )


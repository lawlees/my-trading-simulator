
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from my_trading_simulator.database.models import OptionPosition, TradeIdea

from my_trading_simulator.signals.context import (
    PositionContext,
    get_unambiguous_open_position,
)
from my_trading_simulator.signals.history import (
    MessageContext,
    get_recent_messages,
)
from my_trading_simulator.signals.trade_context import (
    TradeIdeaContext,
    get_active_trade_idea,
)


@dataclass(frozen=True)
class TradingContextSnapshot:
    active_position: PositionContext | None
    active_trade_idea: TradeIdeaContext | None
    recent_messages: list[MessageContext]
    open_position_count: int
    active_trade_idea_count: int
    context_is_valid: bool


def build_trading_context(
    session: Session,
    account_id: int,
    author_id: str,
    channel_id: str,
    before_timestamp: datetime | None = None,
    message_limit: int = 10,
) -> TradingContextSnapshot:
    """
    Build a read-only trading context snapshot.

    Never treat multiple open positions or multiple
    active trade ideas as a valid trading state.
    """
    open_position_count = session.scalar(
        select(func.count())
        .select_from(OptionPosition)
        .where(OptionPosition.account_id == account_id)
        .where(OptionPosition.status == "OPEN")
    ) or 0

    active_trade_idea_count = session.scalar(
        select(func.count())
        .select_from(TradeIdea)
        .where(TradeIdea.account_id == account_id)
        .where(TradeIdea.status == "ACTIVE")
    ) or 0

    context_is_valid = (
        open_position_count <= 1
        and active_trade_idea_count <= 1
    )

    position = get_unambiguous_open_position(
        session=session,
        account_id=account_id,
    )

    trade_idea = get_active_trade_idea(
        session=session,
        account_id=account_id,
    )

    messages = get_recent_messages(
        session=session,
        author_id=author_id,
        channel_id=channel_id,
        limit=message_limit,
        before_timestamp=before_timestamp,
    )

    return TradingContextSnapshot(
        active_position=position,
        active_trade_idea=trade_idea,
        recent_messages=messages,
        open_position_count=open_position_count,
        active_trade_idea_count=active_trade_idea_count,
        context_is_valid=context_is_valid,
    )

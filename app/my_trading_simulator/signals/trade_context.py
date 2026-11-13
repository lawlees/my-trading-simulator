
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from my_trading_simulator.database.models import TradeIdea


@dataclass(frozen=True)
class TradeIdeaContext:
    trade_idea_id: int
    symbol: str
    option_type: str
    size_type: str
    initial_allocation: Decimal
    initial_risk_limit: Decimal
    additions_used: int
    status: str


def get_active_trade_idea(
    session: Session,
    account_id: int,
) -> TradeIdeaContext | None:
    """
    Return an active trade idea only when exactly
    one active idea exists for the account.

    An active idea may have no currently open position
    if its initial entry stopped out.
    """
    ideas = session.scalars(
        select(TradeIdea)
        .where(TradeIdea.account_id == account_id)
        .where(TradeIdea.status == "ACTIVE")
    ).all()

    if len(ideas) != 1:
        return None

    idea = ideas[0]

    return TradeIdeaContext(
        trade_idea_id=idea.id,
        symbol=idea.symbol,
        option_type=idea.option_type,
        size_type=idea.size_type,
        initial_allocation=idea.initial_allocation,
        initial_risk_limit=idea.initial_risk_limit,
        additions_used=idea.additions_used,
        status=idea.status,
    )

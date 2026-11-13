
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from my_trading_simulator.database.models import OptionPosition


@dataclass(frozen=True)
class PositionContext:
    position_id: int
    symbol: str
    option_type: str
    remaining_quantity: int
    profit_take_completed: bool
    profit_take_status: str


def get_unambiguous_open_position(
    session: Session,
    account_id: int,
    symbol: str | None = None,
) -> PositionContext | None:
    """
    Return the currently open position only when
    exactly one matching position exists.

    Never guess between multiple positions.
    """
    query = (
        select(OptionPosition)
        .where(OptionPosition.account_id == account_id)
        .where(OptionPosition.status == "OPEN")
        .where(OptionPosition.remaining_quantity > 0)
    )

    if symbol is not None:
        query = query.where(
            OptionPosition.symbol == symbol.strip().upper()
        )

    positions = session.scalars(query).all()

    if len(positions) != 1:
        return None

    position = positions[0]

    return PositionContext(
        position_id=position.id,
        symbol=position.symbol,
        option_type=position.option_type,
        remaining_quantity=position.remaining_quantity,
        profit_take_completed=position.profit_take_completed,
        profit_take_status=position.profit_take_status,
    )

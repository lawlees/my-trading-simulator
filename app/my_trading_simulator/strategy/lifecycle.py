
from sqlalchemy import update

from my_trading_simulator.database.models import OptionPosition
from my_trading_simulator.database.session import SessionLocal
from decimal import Decimal

from sqlalchemy import select

from my_trading_simulator.config.settings import settings
from my_trading_simulator.execution.paper_broker import _sell_option_in_session
from my_trading_simulator.strategy.profit_taking import calculate_profit_take_quantity
from my_trading_simulator.strategy.stops import calculate_break_even_stop


def claim_profit_take(position_id: int) -> bool:
    """
    Atomically claim the first profit-taking action.

    Returns True only for the first successful claim.
    Returns False for missing, closed, or already claimed positions.

    Does not execute a trade or mark profit-taking complete.
    """

    if type(position_id) is not int or position_id <= 0:
        raise ValueError("Position ID must be a positive integer")

    with SessionLocal.begin() as session:
        result = session.execute(
            update(OptionPosition)
            .where(OptionPosition.id == position_id)
            .where(OptionPosition.status == "OPEN")
            .where(OptionPosition.remaining_quantity > 0)
            .where(OptionPosition.profit_take_status == "PENDING")
            .where(OptionPosition.profit_take_completed.is_(False))
            .values(profit_take_status="CLAIMED")
        )

        return result.rowcount == 1


def complete_profit_take(
    position_id: int,
    fill_price: Decimal,
) -> Decimal:
    """
    Complete a claimed profit-taking action atomically.

    Records a simulated sale, updates lifecycle status,
    and sets the runner's break-even stop.

    Returns realized net P&L.
    """

    if type(position_id) is not int or position_id <= 0:
        raise ValueError("Position ID must be a positive integer")

    with SessionLocal.begin() as session:
        position = session.scalar(
            select(OptionPosition)
            .where(OptionPosition.id == position_id)
            .with_for_update()
        )

        if position is None:
            raise ValueError("Position not found")

        if position.status != "OPEN":
            raise ValueError("Position is not open")

        if position.profit_take_status != "CLAIMED":
            raise ValueError("Profit-taking has not been claimed")

        if position.profit_take_completed:
            raise ValueError("Profit-taking already completed")

        quantity_to_sell = calculate_profit_take_quantity(
            original_quantity=position.quantity,
            remaining_quantity=position.remaining_quantity,
            fraction=settings.profit_take_fraction,
        )

        if quantity_to_sell <= 0:
            raise ValueError("No contracts available to sell")

        realized_pnl = _sell_option_in_session(
            session=session,
            position_id=position_id,
            quantity=quantity_to_sell,
            fill_price=fill_price,
        )

        position.profit_take_status = "COMPLETED"
        position.profit_take_completed = True

        if position.remaining_quantity > 0:
            position.runner_stop_price = calculate_break_even_stop(
                entry_price=position.entry_price,
                contract_multiplier=settings.option_contract_multiplier,
            )
        else:
            position.runner_stop_price = None

        return realized_pnl

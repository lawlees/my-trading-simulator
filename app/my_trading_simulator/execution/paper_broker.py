
from datetime import date
from decimal import Decimal, ROUND_FLOOR

from sqlalchemy import select

from datetime import datetime, timezone

from my_trading_simulator.config.settings import settings
from my_trading_simulator.database.models import (
    AccountTransaction,
    OptionPosition,
    PaperAccount,
    TradeFill,
)
from my_trading_simulator.database.session import SessionLocal


def buy_option(
    account_id: int,
    symbol: str,
    option_type: str,
    strike_price: Decimal,
    expiration_date: date,
    quantity: int,
    fill_price: Decimal,
    stop_price: Decimal,
) -> int:
    """Record a simulated long-option purchase. Never sends broker orders."""

    symbol = symbol.upper()
    option_type = option_type.upper()

    if symbol not in settings.supported_symbols:
        raise ValueError("Unsupported symbol")

    if option_type not in {"CALL", "PUT"}:
        raise ValueError("Option type must be CALL or PUT")

    if expiration_date != date.today():
        raise ValueError("Only 0DTE options are supported")

    if type(quantity) is not int or quantity <= 0:
        raise ValueError("Quantity must be a positive integer")

    if not all(
        isinstance(value, Decimal) and value.is_finite()
        for value in (strike_price, fill_price, stop_price)
    ):
        raise ValueError("Prices must be finite Decimal values")

    if strike_price <= 0 or fill_price <= 0:
        raise ValueError("Strike and fill prices must be positive")

    if stop_price < 0 or stop_price >= fill_price:
        raise ValueError("Stop price must be below the entry price")

    multiplier = Decimal(settings.option_contract_multiplier)
    premium_cost = fill_price * quantity * multiplier
    intended_loss = (fill_price - stop_price) * quantity * multiplier

    # Illustrative commission assumption, configurable later.
    commission = Decimal("0.65") * quantity
    total_cost = premium_cost + commission

    if premium_cost > settings.max_position_allocation:
        raise ValueError("Position exceeds maximum allocation")

    if intended_loss > settings.max_loss_per_trade:
        raise ValueError("Position exceeds intended loss budget")

    with SessionLocal.begin() as session:
        account = session.scalar(
            select(PaperAccount)
            .where(PaperAccount.id == account_id)
            .with_for_update()
        )

        if account is None:
            raise ValueError("Paper account not found")

        if account.cash_balance < total_cost:
            raise ValueError("Insufficient available cash")

        account.cash_balance -= total_cost

        position = OptionPosition(
            account_id=account_id,
            symbol=symbol,
            option_type=option_type,
            strike_price=strike_price,
            expiration_date=expiration_date,
            quantity=quantity,
            remaining_quantity=quantity,
            entry_price=fill_price,
            status="OPEN",
        )
        session.add(position)
        session.flush()

        session.add(
            TradeFill(
                position_id=position.id,
                side="BUY",
                quantity=quantity,
                price=fill_price,
                commission=commission,
            )
        )

        session.add(
            AccountTransaction(
                account_id=account_id,
                transaction_type="OPTION_BUY",
                amount=-total_cost,
                description=f"BUY {quantity} {symbol} {option_type} {strike_price}",
            )
        )

        return position.id
    

def sell_option(
    position_id: int,
    quantity: int,
    fill_price: Decimal,
) -> Decimal:
    """Record a simulated option sale and return realized net P&L."""

    if type(quantity) is not int or quantity <= 0:
        raise ValueError("Sell quantity must be a positive integer")

    if not isinstance(fill_price, Decimal) or not fill_price.is_finite():
        raise ValueError("Fill price must be a finite Decimal")

    if fill_price < 0:
        raise ValueError("Fill price cannot be negative")

    multiplier = Decimal(settings.option_contract_multiplier)
    commission_per_contract = Decimal("0.65")

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

        if quantity > position.remaining_quantity:
            raise ValueError("Cannot sell more contracts than owned")

        account = session.get(PaperAccount, position.account_id)

        sale_proceeds = fill_price * quantity * multiplier
        exit_commission = commission_per_contract * quantity
        net_proceeds = sale_proceeds - exit_commission

        # Allocate the original entry commission to sold contracts.
        entry_commission = commission_per_contract * quantity

        realized_pnl = (
            (fill_price - position.entry_price) * quantity * multiplier
            - entry_commission
            - exit_commission
        )

        account.cash_balance += net_proceeds
        position.remaining_quantity -= quantity

        if position.remaining_quantity == 0:
            position.status = "CLOSED"
            position.closed_at = datetime.now(timezone.utc)

        session.add(
            TradeFill(
                position_id=position.id,
                side="SELL",
                quantity=quantity,
                price=fill_price,
                commission=exit_commission,
            )
        )

        session.add(
            AccountTransaction(
                account_id=account.id,
                transaction_type="OPTION_SELL",
                amount=net_proceeds,
                description=(
                    f"SELL {quantity} {position.symbol} "
                    f"{position.option_type} {position.strike_price}"
                ),
            )
        )

        return realized_pnl


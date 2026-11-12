
from datetime import date
from decimal import Decimal, ROUND_FLOOR

from sqlalchemy import select

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

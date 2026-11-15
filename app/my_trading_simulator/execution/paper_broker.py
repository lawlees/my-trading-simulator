"""Simulated long-option fills only. No real brokerage execution.

SQLite writes use BEGIN IMMEDIATE before reading positions/ideas; this serializes
writers across processes for this database. Never bypass these entry points.
"""

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select, update

from my_trading_simulator.observability.performance import timed
from my_trading_simulator.config.settings import settings
from my_trading_simulator.database.models import (
    AccountTransaction, OptionPosition, PaperAccount, TradeFill, TradeIdea, TradeEvent,
)
from my_trading_simulator.database.session import SessionLocal

COMMISSION_PER_CONTRACT = Decimal("0.65")


def _start_write_transaction(session):
    """Acquire a SQLite database-wide RESERVED write lock before reading state."""
    if session.bind.dialect.name == "sqlite":
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")


def _valid_price(value, *, allow_zero=False):
    return (isinstance(value, Decimal) and value.is_finite()
            and (value >= 0 if allow_zero else value > 0))


def _check_entry(symbol, option_type, strike_price, expiration_date,
                 quantity, fill_price, stop_price):
    if not isinstance(symbol, str) or symbol.strip().upper() not in settings.supported_symbols:
        raise ValueError("Unsupported symbol")
    if not isinstance(option_type, str) or option_type.strip().upper() not in {"CALL", "PUT"}:
        raise ValueError("Option type must be CALL or PUT")
    if expiration_date != datetime.now(ZoneInfo("America/New_York")).date():
        raise ValueError("Only 0DTE options are supported (New York date)")
    if type(quantity) is not int or quantity <= 0:
        raise ValueError("Quantity must be a positive integer")
    if not _valid_price(strike_price) or not _valid_price(fill_price):
        raise ValueError("Strike and fill prices must be finite positive Decimals")
    if not _valid_price(stop_price, allow_zero=True) or stop_price >= fill_price:
        raise ValueError("Stop must be nonnegative and below the entry price")


def _entry_cost_risk(quantity, fill_price, stop_price):
    multiplier = Decimal(settings.option_contract_multiplier)
    premium_cost = quantity * fill_price * multiplier
    planned_loss = quantity * (fill_price - stop_price) * multiplier
    commission = COMMISSION_PER_CONTRACT * quantity
    return premium_cost, planned_loss, commission


def _account_has_open_position(session, account_id):
    return session.scalar(
        select(OptionPosition.id).where(
            OptionPosition.account_id == account_id,
            OptionPosition.status == "OPEN",
            OptionPosition.remaining_quantity > 0,
        ).limit(1)
    ) is not None


def _debit_cash(session, account_id, total_cost):
    result = session.execute(
        update(PaperAccount)
        .where(PaperAccount.id == account_id,
               PaperAccount.cash_balance >= total_cost)
        .values(cash_balance=PaperAccount.cash_balance - total_cost)
    )
    if result.rowcount != 1:
        raise ValueError("Account not found or insufficient available cash")


def _record_trade_event(session, event_type, position, message, **details):
    """Stage an outbox event in the caller's existing SQLite transaction.

    Never publish to Discord here: the publisher runs after commit.
    If this transaction rolls back, the event rolls back with its trade.
    """
    session.add(TradeEvent(
        event_type=event_type,
        account_id=position.account_id,
        position_id=position.id,
        message=message,
        payload=json.dumps(details, sort_keys=True, default=str),
        delivery_status="PENDING",
        delivery_attempts=0,
    ))


def _record_buy(session, account_id, position, quantity, price, commission, entry_type):
    session.add(TradeFill(position_id=position.id, side="BUY",
                          quantity=quantity, price=price, commission=commission))
    session.add(AccountTransaction(
        account_id=account_id, transaction_type="OPTION_BUY",
        amount=-(price * quantity * settings.option_contract_multiplier + commission),
        description=f"{entry_type} BUY {quantity} {position.symbol} "
                    f"{position.option_type} {position.strike_price}",
    ))
    _record_trade_event(
        session, "BUY_FILLED" if entry_type == "INITIAL" else "ADD_FILLED",
        position,
        f"PAPER {entry_type} BUY {quantity} {position.symbol} {position.option_type} "
        f"{position.strike_price} at ${price} (position #{position.id})",
        quantity=quantity, fill_price=price, commission=commission,
        option_symbol=position.option_symbol, trade_idea_id=position.trade_idea_id,
        stop_price=position.stop_price,
    )


def _validate_entry_option_symbol(
    option_symbol: str | None,
    symbol: str,
    option_type: str,
    expiration_date: date,
    strike_price: Decimal,
) -> str | None:
    """Validate the OCC symbol against the entry contract, without substitution.

    None remains permitted for legacy callers/tests, but these positions
    cannot be monitored automatically until an exact symbol is verified.
    """
    if option_symbol is None:
        return None
    if not isinstance(option_symbol, str):
        raise ValueError("Invalid option symbol")

    from my_trading_simulator.market_data.contract_identity import (
        OPTION_SYMBOL_PATTERN,
    )

    normalized = option_symbol.strip().upper()
    match = OPTION_SYMBOL_PATTERN.fullmatch(normalized)
    if match is None:
        raise ValueError("Invalid OCC option symbol")

    encoded_underlying, date_code, type_code, strike_code = match.groups()
    try:
        encoded_date = datetime.strptime(date_code, "%y%m%d").date()
        encoded_strike = Decimal(strike_code) / Decimal("1000")
    except ValueError as exc:
        raise ValueError("Invalid OCC contract details") from exc

    if encoded_underlying != symbol.strip().upper():
        raise ValueError("Option underlying mismatch")
    expected_type_code = {"CALL": "C", "PUT": "P"}.get(option_type.strip().upper())
    if type_code != expected_type_code:
        raise ValueError("Option type mismatch")
    if encoded_date != expiration_date:
        raise ValueError("Option expiration mismatch")
    if encoded_strike != strike_price:
        raise ValueError("Option strike mismatch")

    return normalized

@timed("paper_buy")
def buy_option(
    account_id: int,
    symbol: str,
    option_type: str,
    strike_price: Decimal,
    expiration_date: date,
    quantity: int,
    fill_price: Decimal,
    stop_price: Decimal,
    size_type: str = "NORMAL",
    option_symbol: str | None = None,
) -> int:
    """Open one INITIAL paper position and one persisted trade idea.

    Reject if ANY option position is open in the paper account, including runners.
    """
    _check_entry(symbol, option_type, strike_price, expiration_date,
                 quantity, fill_price, stop_price)
    option_symbol = _validate_entry_option_symbol(
        option_symbol=option_symbol,
        symbol=symbol,
        option_type=option_type,
        expiration_date=expiration_date,
        strike_price=strike_price,
    )
    if type(account_id) is not int or account_id <= 0:
        raise ValueError("Invalid paper account")
    size_type = size_type.upper() if isinstance(size_type, str) else ""
    if size_type not in {"NORMAL", "LIGHT"}:
        raise ValueError("Size type must be NORMAL or LIGHT")

    fraction = settings.light_position_fraction if size_type == "LIGHT" else Decimal("1")
    allocation_limit = settings.max_position_allocation * fraction
    risk_limit = settings.max_loss_per_trade * fraction
    premium, risk, commission = _entry_cost_risk(quantity, fill_price, stop_price)
    if premium > allocation_limit:
        raise ValueError("Position exceeds maximum allocation")
    if risk > risk_limit:
        raise ValueError("Position exceeds intended loss budget")

    with SessionLocal.begin() as session:
        _start_write_transaction(session)
        if session.get(PaperAccount, account_id) is None:
            raise ValueError("Paper account not found")
        if _account_has_open_position(session, account_id):
            raise ValueError("Another option position remains open")
        _debit_cash(session, account_id, premium + commission)

        idea = TradeIdea(
            account_id=account_id, symbol=symbol.strip().upper(),
            option_type=option_type.strip().upper(), size_type=size_type,
            initial_allocation=allocation_limit, initial_risk_limit=risk_limit,
            additions_used=0, status="ACTIVE",
        )
        session.add(idea)
        session.flush()
        position = OptionPosition(
            account_id=account_id, symbol=idea.symbol, option_type=idea.option_type,
            option_symbol=option_symbol, strike_price=strike_price, expiration_date=expiration_date,
            quantity=quantity, remaining_quantity=quantity,
            entry_price=fill_price, stop_price=stop_price,
            status="OPEN", trade_idea_id=idea.id, entry_type="INITIAL",
        )
        session.add(position)
        session.flush()
        _record_buy(session, account_id, position, quantity, fill_price,
                    commission, "INITIAL")
        return position.id


@timed("paper_add")
def add_option(
    trade_idea_id: int,
    strike_price: Decimal,
    expiration_date: date,
    quantity: int,
    fill_price: Decimal,
    stop_price: Decimal,
    option_symbol: str | None = None,
) -> int:
    """One explicitly authorized ADD, either to the open position or after STOP.

    Caller MUST validate a fresh contract and an explicit Casey ADD. Never call
    this automatically on a price movement or from a watchlist.

    When adding to an open position with a persisted OCC symbol, that exact
    symbol is required. Legacy positions without a symbol may still be added
    to by legacy callers, but remain ineligible for automatic stop monitoring.
    """
    if type(trade_idea_id) is not int or trade_idea_id <= 0:
        raise ValueError("Invalid trade idea")
    with SessionLocal.begin() as session:
        _start_write_transaction(session)
        idea = session.get(TradeIdea, trade_idea_id)
        if idea is None or idea.status != "ACTIVE":
            raise ValueError("ADD requires an ACTIVE trade idea")
        _check_entry(idea.symbol, idea.option_type, strike_price,
                     expiration_date, quantity, fill_price, stop_price)
        option_symbol = _validate_entry_option_symbol(
            option_symbol=option_symbol,
            symbol=idea.symbol,
            option_type=idea.option_type,
            expiration_date=expiration_date,
            strike_price=strike_price,
        )
        if idea.additions_used >= settings.max_additions_per_trade:
            raise ValueError("ADD limit reached")

        premium, risk, commission = _entry_cost_risk(quantity, fill_price, stop_price)
        if premium > idea.initial_allocation * settings.add_position_fraction:
            raise ValueError("ADD exceeds allocation limit")
        if risk > idea.initial_risk_limit * settings.add_position_fraction:
            raise ValueError("ADD exceeds risk limit")

        open_position = session.scalar(select(OptionPosition).where(
            OptionPosition.account_id == idea.account_id,
            OptionPosition.status == "OPEN",
            OptionPosition.remaining_quantity > 0,
        ))
        if open_position is not None:
            if open_position.trade_idea_id != idea.id:
                raise ValueError("Independent position already open")
            if open_position.profit_take_completed or open_position.profit_take_status != "PENDING":
                raise ValueError("Cannot ADD after profit-taking begins")
            if (open_position.strike_price != strike_price
                    or open_position.expiration_date != expiration_date
                    or open_position.option_type != idea.option_type):
                raise ValueError("ADD must use the same open option contract")
            if open_position.option_symbol is not None:
                if option_symbol != open_position.option_symbol:
                    raise ValueError("ADD must match the open position's exact option symbol")
        else:
            # A new linked ADD position is allowed only after a confirmed stop exit.
            prior = session.scalars(select(OptionPosition).where(
                OptionPosition.trade_idea_id == idea.id,
            ).order_by(OptionPosition.id.desc())).first()
            if prior is None or prior.status != "CLOSED" or prior.close_reason != "STOP":
                raise ValueError("Reentry ADD requires a stopped-out trade idea")

        _debit_cash(session, idea.account_id, premium + commission)
        if open_position is not None:
            old_quantity = open_position.quantity
            total_quantity = old_quantity + quantity
            open_position.entry_price = (
                open_position.entry_price * old_quantity + fill_price * quantity
            ) / Decimal(total_quantity)
            open_position.stop_price = (
                open_position.stop_price * old_quantity + stop_price * quantity
            ) / Decimal(total_quantity)
            open_position.quantity = total_quantity
            open_position.remaining_quantity += quantity
            if open_position.option_symbol is None:
                open_position.option_symbol = option_symbol
            position = open_position
        else:
            position = OptionPosition(
                account_id=idea.account_id, symbol=idea.symbol,
                option_type=idea.option_type, option_symbol=option_symbol,
                strike_price=strike_price, expiration_date=expiration_date,
                quantity=quantity, remaining_quantity=quantity,
                entry_price=fill_price, stop_price=stop_price,
                trade_idea_id=idea.id, entry_type="ADD", status="OPEN",
            )
            session.add(position)
            session.flush()
        idea.additions_used += 1
        _record_buy(session, idea.account_id, position, quantity, fill_price,
                    commission, "ADD")
        return position.id


def _sell_option_in_session(session, position_id: int, quantity: int,
                            fill_price: Decimal) -> Decimal:
    """Simulate a sale within the caller's transaction. Caller handles commit."""
    if type(quantity) is not int or quantity <= 0:
        raise ValueError("Sell quantity must be a positive integer")
    if not _valid_price(fill_price, allow_zero=True):
        raise ValueError("Fill price must be a finite nonnegative Decimal")
    position = session.scalar(select(OptionPosition).where(
        OptionPosition.id == position_id
    ).with_for_update())
    if position is None or position.status != "OPEN":
        raise ValueError("Position not found or not open")
    if quantity > position.remaining_quantity:
        raise ValueError("Cannot sell more contracts than owned")
    multiplier = Decimal(settings.option_contract_multiplier)
    exit_commission = COMMISSION_PER_CONTRACT * quantity
    net_proceeds = fill_price * quantity * multiplier - exit_commission
    realized_pnl = ((fill_price - position.entry_price) * quantity * multiplier
                    - 2 * exit_commission)
    result = session.execute(update(OptionPosition).where(
        OptionPosition.id == position_id,
        OptionPosition.status == "OPEN",
        OptionPosition.remaining_quantity >= quantity,
    ).values(remaining_quantity=OptionPosition.remaining_quantity - quantity))
    if result.rowcount != 1:
        raise ValueError("Position changed or insufficient contracts")
    session.refresh(position)
    credited = session.execute(update(PaperAccount).where(
        PaperAccount.id == position.account_id,
    ).values(cash_balance=PaperAccount.cash_balance + net_proceeds))
    if credited.rowcount != 1:
        raise ValueError("Paper account not found")
    if position.remaining_quantity == 0:
        position.status = "CLOSED"
        position.closed_at = datetime.now(timezone.utc)
        if position.close_reason is None:
            position.close_reason = "MANUAL"
    session.add(TradeFill(
        position_id=position_id, side="SELL", quantity=quantity,
        price=fill_price, commission=exit_commission,
    ))
    session.add(AccountTransaction(
        account_id=position.account_id, transaction_type="OPTION_SELL",
        amount=net_proceeds,
        description=f"SELL {quantity} {position.symbol} "
                    f"{position.option_type} {position.strike_price}",
    ))
    return realized_pnl


@timed("paper_sell")
def sell_option(position_id: int, quantity: int, fill_price: Decimal) -> Decimal:
    """Simulate an exit; may not be called with a fabricated executable price."""
    with SessionLocal.begin() as session:
        _start_write_transaction(session)
        realized_pnl = _sell_option_in_session(session, position_id, quantity, fill_price)
        position = session.get(OptionPosition, position_id)
        event_type = "POSITION_CLOSED" if position.remaining_quantity == 0 else "PARTIAL_SELL"
        _record_trade_event(
            session, event_type, position,
            f"PAPER SELL {quantity} {position.symbol} {position.option_type} "
            f"{position.strike_price} at ${fill_price} (position #{position.id})",
            quantity=quantity, fill_price=fill_price,
            remaining_quantity=position.remaining_quantity,
            realized_pnl=realized_pnl, close_reason=position.close_reason,
        )
        return realized_pnl


@timed("paper_stop")
def process_option_stop(position_id: int, executable_bid: Decimal) -> bool:
    """Check a supplied VALIDATED option bid and close a triggered paper position.

    A separate market-data monitor must call this repeatedly and validate quote
    timestamp, symbol, spread and market hours BEFORE passing executable_bid.
    True means the complete remaining position was sold in this transaction.
    """
    if not _valid_price(executable_bid, allow_zero=True):
        raise ValueError("Invalid executable bid")
    with SessionLocal.begin() as session:
        _start_write_transaction(session)
        position = session.get(OptionPosition, position_id)
        if position is None or position.status != "OPEN" or position.remaining_quantity <= 0:
            return False
        stop = (position.runner_stop_price if position.profit_take_completed
                else position.stop_price)
        if stop is None or not _valid_price(stop, allow_zero=True):
            raise ValueError("Position has no valid persisted stop")
        if executable_bid > stop:
            return False
        qty = position.remaining_quantity
        realized_pnl = _sell_option_in_session(session, position_id, qty, executable_bid)
        position.close_reason = "STOP"
        _record_trade_event(
            session, "STOP_FILLED", position,
            f"PAPER STOP FILLED {qty} {position.symbol} {position.option_type} "
            f"{position.strike_price} at ${executable_bid} (position #{position.id})",
            quantity=qty, fill_price=executable_bid, stop_price=stop,
            realized_pnl=realized_pnl, remaining_quantity=position.remaining_quantity,
        )
        return True

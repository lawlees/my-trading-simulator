
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from my_trading_simulator.database.models import (
    AccountTransaction,
    Base,
    OptionPosition,
    PaperAccount,
    TradeFill,
)
from my_trading_simulator.execution import paper_broker


@pytest.fixture
def paper_account(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper_test.db'}")
    Base.metadata.create_all(engine)

    test_sessions = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    monkeypatch.setattr(paper_broker, "SessionLocal", test_sessions)

    with test_sessions.begin() as session:
        account = PaperAccount(
            name="Test Account",
            initial_balance=Decimal("7000.00"),
            cash_balance=Decimal("7000.00"),
        )
        session.add(account)
        session.flush()
        account_id = account.id

    yield account_id, test_sessions
    engine.dispose()


def test_buy_option(paper_account):
    account_id, sessions = paper_account

    position_id = paper_broker.buy_option(
        account_id=account_id,
        symbol="SPY",
        option_type="CALL",
        strike_price=Decimal("600"),
        expiration_date=date.today(),
        quantity=4,
        fill_price=Decimal("1.00"),
        stop_price=Decimal("0.65"),
    )

    with sessions() as session:
        account = session.get(PaperAccount, account_id)
        position = session.get(OptionPosition, position_id)
        fills = session.scalars(select(TradeFill)).all()
        transactions = session.scalars(select(AccountTransaction)).all()

        assert account.cash_balance == Decimal("6597.40")
        assert position.remaining_quantity == 4
        assert position.status == "OPEN"
        assert len(fills) == 1
        assert fills[0].side == "BUY"
        assert len(transactions) == 1
        assert transactions[0].amount == Decimal("-402.60")


def test_reject_excess_allocation(paper_account):
    account_id, sessions = paper_account

    with pytest.raises(ValueError, match="maximum allocation"):
        paper_broker.buy_option(
            account_id=account_id,
            symbol="SPY",
            option_type="CALL",
            strike_price=Decimal("600"),
            expiration_date=date.today(),
            quantity=5,
            fill_price=Decimal("1.00"),
            stop_price=Decimal("0.75"),
        )

    with sessions() as session:
        assert session.get(PaperAccount, account_id).cash_balance == Decimal("7000.00")
        assert session.scalars(select(OptionPosition)).first() is None


def test_reject_excess_risk(paper_account):
    account_id, sessions = paper_account

    with pytest.raises(ValueError, match="intended loss budget"):
        paper_broker.buy_option(
            account_id=account_id,
            symbol="SPY",
            option_type="CALL",
            strike_price=Decimal("600"),
            expiration_date=date.today(),
            quantity=4,
            fill_price=Decimal("1.00"),
            stop_price=Decimal("0.50"),
        )

    with sessions() as session:
        assert session.get(PaperAccount, account_id).cash_balance == Decimal("7000.00")
        assert session.scalars(select(OptionPosition)).first() is None



def test_partial_and_full_exit(paper_account):
    account_id, sessions = paper_account

    # Buy 4 contracts at $1.00
    position_id = paper_broker.buy_option(
        account_id=account_id,
        symbol="SPY",
        option_type="CALL",
        strike_price=Decimal("600"),
        expiration_date=date.today(),
        quantity=4,
        fill_price=Decimal("1.00"),
        stop_price=Decimal("0.65"),
    )

    # Sell 3 contracts at $1.50
    partial_pnl = paper_broker.sell_option(
        position_id=position_id,
        quantity=3,
        fill_price=Decimal("1.50"),
    )

    assert partial_pnl == Decimal("146.10")

    with sessions() as session:
        position = session.get(OptionPosition, position_id)
        account = session.get(PaperAccount, account_id)

        assert position.remaining_quantity == 1
        assert position.status == "OPEN"
        assert account.cash_balance == Decimal("7045.45")

    # Sell remaining contract at $1.80
    final_pnl = paper_broker.sell_option(
        position_id=position_id,
        quantity=1,
        fill_price=Decimal("1.80"),
    )

    assert final_pnl == Decimal("78.70")

    with sessions() as session:
        position = session.get(OptionPosition, position_id)
        account = session.get(PaperAccount, account_id)

        assert position.remaining_quantity == 0
        assert position.status == "CLOSED"
        assert position.closed_at is not None
        assert account.cash_balance == Decimal("7224.80")

        fills = session.scalars(
            select(TradeFill)
            .where(TradeFill.position_id == position_id)
            .order_by(TradeFill.id)
        ).all()

        assert len(fills) == 3
        assert [fill.side for fill in fills] == [
            "BUY", "SELL", "SELL"
        ]

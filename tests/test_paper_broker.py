
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


def test_concurrent_sales_cannot_oversell(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import date

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session, sessionmaker

    from my_trading_simulator.database.models import (
        Base,
        PaperAccount,
        OptionPosition,
        TradeFill,
    )
    from my_trading_simulator.execution import paper_broker

    # Create an isolated test database.
    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'concurrent_sales.db'}",
        connect_args={"timeout": 5},
    )

    Base.metadata.create_all(test_engine)

    test_sessions = sessionmaker(
        bind=test_engine,
        class_=Session,
        expire_on_commit=False,
    )

    monkeypatch.setattr(
        paper_broker,
        "SessionLocal",
        test_sessions,
    )

    # Create an account and a position with 4 contracts.
    with test_sessions.begin() as session:
        account = PaperAccount(
            name="Concurrent Sales Test",
            initial_balance=Decimal("7000"),
            cash_balance=Decimal("7000"),
        )
        session.add(account)
        session.flush()

        position = OptionPosition(
            account_id=account.id,
            symbol="SPY",
            option_type="CALL",
            strike_price=Decimal("600"),
            expiration_date=date.today(),
            quantity=4,
            remaining_quantity=4,
            entry_price=Decimal("1.00"),
            status="OPEN",
            profit_take_completed=False,
            profit_take_status="PENDING",
        )
        session.add(position)
        session.flush()

        position_id = position.id
        account_id = account.id

    # Both workers attempt to sell 3 contracts.
    def attempt_sale():
        try:
            paper_broker.sell_option(
                position_id=position_id,
                quantity=3,
                fill_price=Decimal("1.50"),
            )
            return "SUCCESS"
        except ValueError:
            return "REJECTED"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: attempt_sale(),
                range(2),
            )
        )

    assert sorted(results) == ["REJECTED", "SUCCESS"]

    # Confirm only 3 contracts were sold.
    with test_sessions() as session:
        position = session.get(OptionPosition, position_id)
        account = session.get(PaperAccount, account_id)

        from sqlalchemy import select

        sell_fills = session.scalars(
            select(TradeFill).where(
                TradeFill.position_id == position_id,
                TradeFill.side == "SELL",
            )
        ).all()

        assert position.remaining_quantity == 1
        assert position.status == "OPEN"
        assert account.cash_balance == Decimal("7448.05")
        assert len(sell_fills) == 1
        assert sell_fills[0].quantity == 3

    test_engine.dispose()


def test_concurrent_purchases_cannot_overspend(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import date

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session, sessionmaker

    from my_trading_simulator.database.models import (
        Base,
        PaperAccount,
        OptionPosition,
        TradeFill,
    )
    from my_trading_simulator.execution import paper_broker

    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'concurrent_buys.db'}",
        connect_args={"timeout": 5},
    )

    Base.metadata.create_all(test_engine)

    test_sessions = sessionmaker(
        bind=test_engine,
        class_=Session,
        expire_on_commit=False,
    )

    monkeypatch.setattr(
        paper_broker,
        "SessionLocal",
        test_sessions,
    )

    with test_sessions.begin() as session:
        account = PaperAccount(
            name="Concurrent Purchases Test",
            initial_balance=Decimal("500"),
            cash_balance=Decimal("500"),
        )
        session.add(account)
        session.flush()
        account_id = account.id

    def attempt_purchase():
        try:
            paper_broker.buy_option(
                account_id=account_id,
                symbol="SPY",
                option_type="CALL",
                strike_price=Decimal("600"),
                expiration_date=date.today(),
                quantity=4,
                fill_price=Decimal("1.00"),
                stop_price=Decimal("0.65"),
            )
            return "SUCCESS"
        except ValueError:
            return "REJECTED"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: attempt_purchase(),
                range(2),
            )
        )

    assert sorted(results) == ["REJECTED", "SUCCESS"]

    with test_sessions() as session:
        account = session.get(PaperAccount, account_id)

        positions = session.scalars(
            select(OptionPosition).where(
                OptionPosition.account_id == account_id
            )
        ).all()

        buy_fills = session.scalars(
            select(TradeFill).where(
                TradeFill.side == "BUY"
            )
        ).all()

        assert account.cash_balance == Decimal("97.40")
        assert len(positions) == 1
        assert len(buy_fills) == 1
        assert buy_fills[0].quantity == 4

    test_engine.dispose()

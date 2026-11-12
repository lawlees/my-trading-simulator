from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from my_trading_simulator.database.models import (
    AccountTransaction,
    Base,
    PaperAccount,
)
from my_trading_simulator.portfolio import account as account_module


@pytest.fixture
def test_account(tmp_path, monkeypatch):
    database_path = tmp_path / "test_account.db"
    engine = create_engine(f"sqlite:///{database_path}")

    Base.metadata.create_all(engine)

    test_session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    monkeypatch.setattr(
        account_module,
        "SessionLocal",
        test_session_factory,
    )

    with test_session_factory.begin() as session:
        account = PaperAccount(
            name="Test Paper Account",
            initial_balance=Decimal("7000.00"),
            cash_balance=Decimal("7000.00"),
        )
        session.add(account)
        session.flush()
        account_id = account.id

    yield account_id, test_session_factory

    engine.dispose()


def test_deposit_and_withdrawal(test_account):
    account_id, session_factory = test_account

    balance = account_module.record_cash_transaction(
        account_id=account_id,
        transaction_type="DEPOSIT",
        amount=Decimal("100.00"),
        description="Test deposit",
    )

    assert balance == Decimal("7100.00")

    balance = account_module.record_cash_transaction(
        account_id=account_id,
        transaction_type="WITHDRAWAL",
        amount=Decimal("-100.00"),
        description="Test withdrawal",
    )

    assert balance == Decimal("7000.00")

    with session_factory() as session:
        transactions = session.scalars(
            select(AccountTransaction).order_by(AccountTransaction.id)
        ).all()

        assert len(transactions) == 2
        assert transactions[0].amount == Decimal("100.00")
        assert transactions[1].amount == Decimal("-100.00")


def test_insufficient_cash_rolls_back(test_account):
    account_id, session_factory = test_account

    with pytest.raises(ValueError, match="insufficient cash"):
        account_module.record_cash_transaction(
            account_id=account_id,
            transaction_type="WITHDRAWAL",
            amount=Decimal("-8000.00"),
            description="Invalid withdrawal",
        )

    with session_factory() as session:
        account = session.get(PaperAccount, account_id)

        assert account.cash_balance == Decimal("7000.00")
        assert session.scalar(
            select(AccountTransaction.id)
        ) is None
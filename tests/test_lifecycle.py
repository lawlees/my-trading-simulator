
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from my_trading_simulator.database.models import (
    Base,
    OptionPosition,
    PaperAccount,
)
from my_trading_simulator.strategy import lifecycle


@pytest.fixture
def test_position(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'lifecycle_test.db'}"
    )

    Base.metadata.create_all(engine)

    test_sessions = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    monkeypatch.setattr(
        lifecycle,
        "SessionLocal",
        test_sessions,
    )

    with test_sessions.begin() as session:
        account = PaperAccount(
            name="Lifecycle Test Account",
            initial_balance=Decimal("7000.00"),
            cash_balance=Decimal("7000.00"),
        )
        session.add(account)
        session.flush()

        position = OptionPosition(
            account_id=account.id,
            symbol="SPY",
            option_type="CALL",
            strike_price=Decimal("600"),
            expiration_date=__import__("datetime").date.today(),
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

    yield position_id, account_id, test_sessions

    engine.dispose()


def test_first_claim_succeeds(test_position):
    position_id, _, sessions = test_position

    result = lifecycle.claim_profit_take(position_id)

    assert result is True

    with sessions() as session:
        position = session.get(OptionPosition, position_id)

        assert position.profit_take_status == "CLAIMED"
        assert position.profit_take_completed is False


def test_duplicate_claim_rejected(test_position):
    position_id, _, sessions = test_position

    first = lifecycle.claim_profit_take(position_id)
    second = lifecycle.claim_profit_take(position_id)

    assert first is True
    assert second is False

    with sessions() as session:
        position = session.get(OptionPosition, position_id)

        assert position.profit_take_status == "CLAIMED"


def test_claim_does_not_change_cash(test_position):
    position_id, account_id, sessions = test_position

    lifecycle.claim_profit_take(position_id)

    with sessions() as session:
        account = session.get(PaperAccount, account_id)

        assert account.cash_balance == Decimal("7000.00")


def test_missing_position_rejected(test_position):
    result = lifecycle.claim_profit_take(999999)

    assert result is False


def test_invalid_position_id(test_position):
    with pytest.raises(ValueError):
        lifecycle.claim_profit_take(0)


def test_complete_profit_take(test_position, monkeypatch):
    position_id, account_id, sessions = test_position

    # Make the paper broker use the same temporary database.
    from my_trading_simulator.execution import paper_broker

    monkeypatch.setattr(
        paper_broker,
        "SessionLocal",
        sessions,
    )

    # Simulate Casey's first profit-taking signal.
    assert lifecycle.claim_profit_take(position_id) is True

    # Simulate selling 75% at $1.50 per option.
    realized_pnl = lifecycle.complete_profit_take(
        position_id=position_id,
        fill_price=Decimal("1.50"),
    )

    assert realized_pnl == Decimal("146.10")

    with sessions() as session:
        position = session.get(OptionPosition, position_id)
        account = session.get(PaperAccount, account_id)

        assert position.quantity == 4
        assert position.remaining_quantity == 1
        assert position.status == "OPEN"

        assert position.profit_take_status == "COMPLETED"
        assert position.profit_take_completed is True
        assert position.runner_stop_price == Decimal("1.02")

        # Fixture starts with $7,000 cash and an existing
        # position. It does not deduct an entry purchase.
        assert account.cash_balance == Decimal("7448.05")


def test_duplicate_profit_take_cannot_sell_runner(test_position):
    position_id, account_id, sessions = test_position

    assert lifecycle.claim_profit_take(position_id) is True

    lifecycle.complete_profit_take(
        position_id=position_id,
        fill_price=Decimal("1.50"),
    )

    # A second claim must be rejected.
    assert lifecycle.claim_profit_take(position_id) is False

    # A second completion must also be rejected.
    with pytest.raises(
        ValueError,
        match="Profit-taking has not been claimed",
    ):
        lifecycle.complete_profit_take(
            position_id=position_id,
            fill_price=Decimal("1.80"),
        )

    with sessions() as session:
        position = session.get(OptionPosition, position_id)
        account = session.get(PaperAccount, account_id)

        assert position.remaining_quantity == 1
        assert position.profit_take_status == "COMPLETED"
        assert account.cash_balance == Decimal("7448.05")



def test_end_to_end_trade_lifecycle(
    test_position,
    monkeypatch,
):
    from datetime import date
    from sqlalchemy import select

    from my_trading_simulator.execution import paper_broker
    from my_trading_simulator.database.models import TradeFill

    _, account_id, sessions = test_position

    monkeypatch.setattr(
        paper_broker,
        "SessionLocal",
        sessions,
    )

    # Create a new simulated purchase.
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

    # Initial purchase: $400 premium + $2.60 commission.
    with sessions() as session:
        account = session.get(PaperAccount, account_id)
        assert account.cash_balance == Decimal("6597.40")

    # Casey announces profit-taking.
    assert lifecycle.claim_profit_take(position_id) is True

    partial_pnl = lifecycle.complete_profit_take(
        position_id=position_id,
        fill_price=Decimal("1.50"),
    )

    assert partial_pnl == Decimal("146.10")

    with sessions() as session:
        position = session.get(OptionPosition, position_id)
        account = session.get(PaperAccount, account_id)

        assert position.remaining_quantity == 1
        assert position.profit_take_status == "COMPLETED"
        assert position.runner_stop_price == Decimal("1.02")
        assert account.cash_balance == Decimal("7045.45")

    # Casey announces a full exit.
    final_pnl = paper_broker.sell_option(
        position_id=position_id,
        quantity=1,
        fill_price=Decimal("1.80"),
    )

    assert final_pnl == Decimal("78.70")

    with sessions() as session:
        position = session.get(OptionPosition, position_id)
        account = session.get(PaperAccount, account_id)

        fills = session.scalars(
            select(TradeFill)
            .where(TradeFill.position_id == position_id)
            .order_by(TradeFill.id)
        ).all()

        assert position.status == "CLOSED"
        assert position.remaining_quantity == 0
        assert account.cash_balance == Decimal("7224.80")

        assert [fill.side for fill in fills] == [
            "BUY",
            "SELL",
            "SELL",
        ]


def test_concurrent_profit_take_claims(test_position):
    from concurrent.futures import ThreadPoolExecutor

    position_id, _, sessions = test_position

    # Simulate two workers processing the same signal.
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                lifecycle.claim_profit_take,
                position_id,
            )
            for _ in range(2)
        ]

        results = [future.result() for future in futures]

    # Exactly one worker should claim the position.
    assert sorted(results) == [False, True]

    with sessions() as session:
        position = session.get(OptionPosition, position_id)

        assert position.profit_take_status == "CLAIMED"
        assert position.profit_take_completed is False


from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from my_trading_simulator.database.models import (
    Base,
    OptionPosition,
    PaperAccount,
)
from my_trading_simulator.signals.context import (
    get_unambiguous_open_position,
)


@pytest.fixture
def db(tmp_path):
    """Create an isolated database for each test."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'context_test.db'}"
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session.begin() as session:
        session.add_all([
            PaperAccount(
                name="Account A",
                initial_balance=Decimal("7000"),
                cash_balance=Decimal("7000"),
            ),
            PaperAccount(
                name="Account B",
                initial_balance=Decimal("7000"),
                cash_balance=Decimal("7000"),
            ),
        ])

    yield Session
    engine.dispose()


def add_position(
    session,
    account_id=1,
    symbol="SPY",
    status="OPEN",
    remaining=4,
):
    position = OptionPosition(
        account_id=account_id,
        symbol=symbol,
        option_type="CALL",
        strike_price=Decimal("600"),
        expiration_date=date.today(),
        quantity=4,
        remaining_quantity=remaining,
        entry_price=Decimal("1.00"),
        status=status,
    )
    session.add(position)
    session.flush()
    return position.id


def test_no_open_position(db):
    with db() as session:
        result = get_unambiguous_open_position(session, 1)
        assert result is None


def test_one_open_position(db):
    with db.begin() as session:
        position_id = add_position(session)

    with db() as session:
        result = get_unambiguous_open_position(session, 1)

        assert result is not None
        assert result.position_id == position_id
        assert result.symbol == "SPY"
        assert result.option_type == "CALL"
        assert result.remaining_quantity == 4


def test_multiple_open_positions_are_ambiguous(db):
    # Defensive test: our trading policy will prohibit
    # this situation, but context must never guess.
    with db.begin() as session:
        add_position(session, symbol="SPY")
        add_position(session, symbol="QQQ")

    with db() as session:
        assert get_unambiguous_open_position(session, 1) is None


def test_symbol_filter(db):
    with db.begin() as session:
        add_position(session, symbol="SPY")
        qqq_id = add_position(session, symbol="QQQ")

    with db() as session:
        result = get_unambiguous_open_position(
            session, 1, symbol="qqq"
        )

        assert result is not None
        assert result.position_id == qqq_id
        assert result.symbol == "QQQ"


def test_closed_position_is_ignored(db):
    with db.begin() as session:
        add_position(session, status="CLOSED")

    with db() as session:
        assert get_unambiguous_open_position(session, 1) is None


def test_zero_remaining_contracts_are_ignored(db):
    with db.begin() as session:
        add_position(session, remaining=0)

    with db() as session:
        assert get_unambiguous_open_position(session, 1) is None


def test_positions_are_isolated_by_account(db):
    with db.begin() as session:
        add_position(session, account_id=2)

    with db() as session:
        assert get_unambiguous_open_position(session, 1) is None

        result = get_unambiguous_open_position(session, 2)
        assert result is not None
        assert result.symbol == "SPY"

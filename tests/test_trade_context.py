
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from my_trading_simulator.database.models import (
    Base,
    PaperAccount,
    TradeIdea,
)
from my_trading_simulator.signals.trade_context import (
    get_active_trade_idea,
)


@pytest.fixture
def db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'trade_context_test.db'}"
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


def add_idea(
    session,
    account_id=1,
    symbol="SPY",
    status="ACTIVE",
    additions_used=0,
):
    idea = TradeIdea(
        account_id=account_id,
        symbol=symbol,
        option_type="CALL",
        size_type="NORMAL",
        initial_allocation=Decimal("400"),
        initial_risk_limit=Decimal("150"),
        additions_used=additions_used,
        status=status,
    )
    session.add(idea)
    session.flush()
    return idea.id


def test_no_active_idea(db):
    with db() as session:
        assert get_active_trade_idea(session, 1) is None


def test_one_active_idea(db):
    with db.begin() as session:
        idea_id = add_idea(session)

    with db() as session:
        result = get_active_trade_idea(session, 1)

    assert result is not None
    assert result.trade_idea_id == idea_id
    assert result.symbol == "SPY"
    assert result.option_type == "CALL"
    assert result.initial_allocation == Decimal("400")
    assert result.initial_risk_limit == Decimal("150")
    assert result.additions_used == 0


def test_closed_idea_is_ignored(db):
    with db.begin() as session:
        add_idea(session, status="CLOSED")

    with db() as session:
        assert get_active_trade_idea(session, 1) is None


def test_multiple_active_ideas_are_ambiguous(db):
    with db.begin() as session:
        add_idea(session, symbol="SPY")
        add_idea(session, symbol="QQQ")

    with db() as session:
        assert get_active_trade_idea(session, 1) is None


def test_account_isolation(db):
    with db.begin() as session:
        add_idea(session, account_id=2)

    with db() as session:
        assert get_active_trade_idea(session, 1) is None
        assert get_active_trade_idea(session, 2) is not None


def test_addition_count_is_preserved(db):
    with db.begin() as session:
        add_idea(session, additions_used=1)

    with db() as session:
        result = get_active_trade_idea(session, 1)

    assert result is not None
    assert result.additions_used == 1


def test_idea_remains_active_after_position_closes(db):
    """
    An ACTIVE trade idea can exist even when no
    option position is currently open.
    """
    with db.begin() as session:
        idea_id = add_idea(session)

    with db() as session:
        result = get_active_trade_idea(session, 1)

    assert result is not None
    assert result.trade_idea_id == idea_id
    assert result.status == "ACTIVE"

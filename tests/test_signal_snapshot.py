
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from my_trading_simulator.database.models import (
    Base,
    DiscordMessage,
    OptionPosition,
    PaperAccount,
    TradeIdea,
)
from my_trading_simulator.signals.snapshot import (
    build_trading_context,
)


BASE_TIME = datetime(
    2026, 11, 12, 15, 0, tzinfo=timezone.utc
)


@pytest.fixture
def db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'snapshot_test.db'}"
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session.begin() as session:
        session.add(
            PaperAccount(
                name="Snapshot Test Account",
                initial_balance=Decimal("7000"),
                cash_balance=Decimal("7000"),
            )
        )

    yield Session
    engine.dispose()


def add_trade_idea(session, additions_used=0):
    idea = TradeIdea(
        account_id=1,
        symbol="SPY",
        option_type="CALL",
        size_type="NORMAL",
        initial_allocation=Decimal("400"),
        initial_risk_limit=Decimal("150"),
        additions_used=additions_used,
        status="ACTIVE",
    )
    session.add(idea)
    session.flush()
    return idea.id


def add_position(session, trade_idea_id, status="OPEN"):
    position = OptionPosition(
        account_id=1,
        trade_idea_id=trade_idea_id,
        entry_type="INITIAL",
        symbol="SPY",
        option_type="CALL",
        strike_price=Decimal("600"),
        expiration_date=date.today(),
        quantity=4,
        remaining_quantity=4 if status == "OPEN" else 0,
        entry_price=Decimal("1.00"),
        status=status,
    )
    session.add(position)
    session.flush()
    return position.id


def add_message(
    session,
    message_id,
    text,
    minutes,
    trade_idea_id=None,
    position_id=None,
):
    session.add(
        DiscordMessage(
            discord_message_id=message_id,
            author_id="casey",
            channel_id="trading",
            message_text=text,
            message_timestamp=BASE_TIME + timedelta(minutes=minutes),
            trade_idea_id=trade_idea_id,
            position_id=position_id,
        )
    )


def test_empty_snapshot(db):
    with db() as session:
        snapshot = build_trading_context(
            session, 1, "casey", "trading"
        )

    assert snapshot.active_position is None
    assert snapshot.active_trade_idea is None
    assert snapshot.recent_messages == []


def test_snapshot_with_open_position(db):
    with db.begin() as session:
        idea_id = add_trade_idea(session)
        position_id = add_position(session, idea_id)

        add_message(
            session,
            "100",
            "Taking SPY calls here",
            0,
            trade_idea_id=idea_id,
            position_id=position_id,
        )
        add_message(
            session,
            "101",
            "13 EMA holding nicely",
            5,
            trade_idea_id=idea_id,
        )

    with db() as session:
        snapshot = build_trading_context(
            session, 1, "casey", "trading"
        )

    assert snapshot.active_position is not None
    assert snapshot.active_position.position_id == position_id
    assert snapshot.active_position.symbol == "SPY"

    assert snapshot.active_trade_idea is not None
    assert snapshot.active_trade_idea.trade_idea_id == idea_id

    assert len(snapshot.recent_messages) == 2
    assert snapshot.recent_messages[0].message_text == (
        "Taking SPY calls here"
    )
    assert snapshot.recent_messages[1].message_text == (
        "13 EMA holding nicely"
    )


def test_snapshot_after_stop_out(db):
    with db.begin() as session:
        idea_id = add_trade_idea(session)
        add_position(session, idea_id, status="CLOSED")

        add_message(
            session,
            "200",
            "Taking SPY calls here",
            0,
            trade_idea_id=idea_id,
        )
        add_message(
            session,
            "201",
            "Stopped out",
            5,
            trade_idea_id=idea_id,
        )

    with db() as session:
        snapshot = build_trading_context(
            session, 1, "casey", "trading"
        )

    assert snapshot.active_position is None

    assert snapshot.active_trade_idea is not None
    assert snapshot.active_trade_idea.trade_idea_id == idea_id
    assert snapshot.active_trade_idea.additions_used == 0

    assert len(snapshot.recent_messages) == 2


def test_snapshot_respects_message_cutoff(db):
    with db.begin() as session:
        add_message(session, "300", "First message", 0)
        add_message(session, "301", "Second message", 5)
        add_message(session, "302", "Third message", 10)

    cutoff = BASE_TIME + timedelta(minutes=10)

    with db() as session:
        snapshot = build_trading_context(
            session,
            1,
            "casey",
            "trading",
            before_timestamp=cutoff,
        )

    assert [
        message.message_text
        for message in snapshot.recent_messages
    ] == ["First message", "Second message"]


def test_snapshot_respects_message_limit(db):
    with db.begin() as session:
        for i in range(5):
            add_message(
                session,
                str(400 + i),
                f"Message {i}",
                i,
            )

    with db() as session:
        snapshot = build_trading_context(
            session,
            1,
            "casey",
            "trading",
            message_limit=2,
        )

    assert len(snapshot.recent_messages) == 2
    assert [
        message.message_text
        for message in snapshot.recent_messages
    ] == ["Message 3", "Message 4"]


def test_multiple_open_positions_invalidate_context(db):
    """
    Multiple open positions violate our
    single-position trading policy.
    """
    with db.begin() as session:
        idea_id = add_trade_idea(session)

        add_position(session, idea_id)
        add_position(session, idea_id)

    with db() as session:
        snapshot = build_trading_context(
            session, 1, "casey", "trading"
        )

    assert snapshot.open_position_count == 2
    assert snapshot.context_is_valid is False
    assert snapshot.active_position is None


def test_multiple_active_ideas_invalidate_context(db):
    """
    Multiple active trade ideas must not be
    treated as a safe trading state.
    """
    with db.begin() as session:
        add_trade_idea(session)

        second_idea = TradeIdea(
            account_id=1,
            symbol="QQQ",
            option_type="PUT",
            size_type="NORMAL",
            initial_allocation=Decimal("400"),
            initial_risk_limit=Decimal("150"),
            additions_used=0,
            status="ACTIVE",
        )
        session.add(second_idea)

    with db() as session:
        snapshot = build_trading_context(
            session, 1, "casey", "trading"
        )

    assert snapshot.active_trade_idea_count == 2
    assert snapshot.context_is_valid is False
    assert snapshot.active_trade_idea is None

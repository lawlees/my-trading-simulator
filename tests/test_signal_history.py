
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from my_trading_simulator.database.models import (
    Base,
    DiscordMessage,
)
from my_trading_simulator.signals.history import get_recent_messages


@pytest.fixture
def db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'history_test.db'}"
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    yield Session

    engine.dispose()


BASE_TIME = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)


def add_message(
    session,
    message_id,
    text,
    minutes=0,
    author="casey",
    channel="trading",
    action=None,
):
    message = DiscordMessage(
        discord_message_id=message_id,
        author_id=author,
        channel_id=channel,
        message_text=text,
        message_timestamp=BASE_TIME + timedelta(minutes=minutes),
        action=action,
    )
    session.add(message)


def test_empty_history(db):
    with db() as session:
        result = get_recent_messages(
            session, "casey", "trading"
        )
        assert result == []


def test_messages_are_chronological(db):
    with db.begin() as session:
        add_message(session, "3", "Adding here", 10)
        add_message(session, "1", "Taking SPY calls", 0)
        add_message(session, "2", "13 EMA holding", 5)

    with db() as session:
        result = get_recent_messages(
            session, "casey", "trading"
        )

    assert [m.discord_message_id for m in result] == [
        "1", "2", "3"
    ]


def test_author_isolation(db):
    with db.begin() as session:
        add_message(session, "1", "Casey trade")
        add_message(
            session, "2", "Another trader",
            author="other_trader",
        )

    with db() as session:
        result = get_recent_messages(
            session, "casey", "trading"
        )

    assert len(result) == 1
    assert result[0].message_text == "Casey trade"


def test_channel_isolation(db):
    with db.begin() as session:
        add_message(session, "1", "Trading message")
        add_message(
            session, "2", "General chat",
            channel="general",
        )

    with db() as session:
        result = get_recent_messages(
            session, "casey", "trading"
        )

    assert len(result) == 1
    assert result[0].message_text == "Trading message"


def test_limit_returns_most_recent(db):
    with db.begin() as session:
        for i in range(5):
            add_message(
                session, str(i), f"Message {i}", i
            )

    with db() as session:
        result = get_recent_messages(
            session, "casey", "trading", limit=2
        )

    assert [m.message_text for m in result] == [
        "Message 3", "Message 4"
    ]


def test_before_timestamp(db):
    with db.begin() as session:
        add_message(session, "1", "First", 0)
        add_message(session, "2", "Second", 5)
        add_message(session, "3", "Third", 10)

    cutoff = BASE_TIME + timedelta(minutes=10)

    with db() as session:
        result = get_recent_messages(
            session,
            "casey",
            "trading",
            before_timestamp=cutoff,
        )

    assert [m.message_text for m in result] == [
        "First", "Second"
    ]


def test_invalid_limit(db):
    with db() as session:
        with pytest.raises(ValueError):
            get_recent_messages(
                session, "casey", "trading", limit=0
            )

        with pytest.raises(ValueError):
            get_recent_messages(
                session, "casey", "trading", limit=51
            )

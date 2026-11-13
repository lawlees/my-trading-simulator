
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from my_trading_simulator.database.models import (
    Base,
    DiscordMessage,
)
from my_trading_simulator.signals.storage import (
    save_discord_message,
)


@pytest.fixture
def db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'storage_test.db'}"
    )
    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)

    yield Session

    engine.dispose()


TIMESTAMP = datetime(
    2026, 11, 12, 15, 0, tzinfo=timezone.utc
)


def save(
    session,
    message_id="123",
    text="Taking SPY calls here",
):
    return save_discord_message(
        session=session,
        message_id=message_id,
        author_id="casey",
        channel_id="trading",
        message_text=text,
        message_timestamp=TIMESTAMP,
    )


def test_save_new_message(db):
    with db.begin() as session:
        result = save(session)

    assert result is True

    with db() as session:
        messages = session.scalars(
            select(DiscordMessage)
        ).all()

    assert len(messages) == 1
    assert messages[0].discord_message_id == "123"
    assert messages[0].message_text == (
        "Taking SPY calls here"
    )
    assert messages[0].processing_status == "RECEIVED"


def test_duplicate_message_is_rejected(db):
    with db.begin() as session:
        assert save(session) is True

    with db.begin() as session:
        assert save(session) is False

    with db() as session:
        messages = session.scalars(
            select(DiscordMessage)
        ).all()

    assert len(messages) == 1


def test_different_messages_are_saved(db):
    with db.begin() as session:
        assert save(session, "123") is True
        assert save(session, "124", "Adding here") is True

    with db() as session:
        messages = session.scalars(
            select(DiscordMessage)
        ).all()

    assert len(messages) == 2


def test_empty_message_id_rejected(db):
    with db.begin() as session:
        with pytest.raises(ValueError):
            save(session, message_id="   ")


def test_naive_timestamp_rejected(db):
    with db.begin() as session:
        with pytest.raises(ValueError):
            save_discord_message(
                session=session,
                message_id="123",
                author_id="casey",
                channel_id="trading",
                message_text="Taking SPY calls",
                message_timestamp=datetime(2026, 11, 12),
            )


def test_rollback_does_not_save_message(db):
    with pytest.raises(RuntimeError):
        with db.begin() as session:
            assert save(session) is True
            raise RuntimeError("Simulated processing failure")

    with db() as session:
        messages = session.scalars(
            select(DiscordMessage)
        ).all()

    assert messages == []


def test_duplicate_in_same_transaction(db):
    with db.begin() as session:
        assert save(session) is True
        assert save(session) is False

    with db() as session:
        messages = session.scalars(
            select(DiscordMessage)
        ).all()

    assert len(messages) == 1

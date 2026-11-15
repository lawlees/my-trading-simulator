
"""Tests for persistent dry-run notification classification."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from my_trading_simulator.database.models import (
    Base,
    IncomingNotification,
)
from my_trading_simulator.ingestion import (
    persistent_classification_worker as worker,
)


def make_session_factory():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def add_notification(session_factory, status, age_seconds):
    received_at = datetime.now(timezone.utc) - timedelta(
        seconds=age_seconds
    )

    with session_factory() as session:
        item = IncomingNotification(
            source="MANUAL_ENTRY",
            idempotency_key=f"test-{status}-{age_seconds}",
            message_text="Test commentary. No trade.",
            received_at=received_at,
            processing_status=status,
        )
        session.add(item)
        session.commit()
        return item.id


def test_selects_oldest_recent_notification():
    sessions = make_session_factory()

    first_id = add_notification(sessions, "RECEIVED", 30)
    add_notification(sessions, "RECEIVED", 300)
    add_notification(sessions, "FAILED_CLASSIFICATION", 10)

    assert worker.get_next_notification_id(
        max_age_seconds=120,
        session_factory=sessions,
    ) == first_id


def test_skips_stale_notifications():
    sessions = make_session_factory()

    add_notification(sessions, "RECEIVED", 300)

    assert worker.get_next_notification_id(
        max_age_seconds=120,
        session_factory=sessions,
    ) is None


def test_skips_failed_notifications():
    sessions = make_session_factory()

    add_notification(sessions, "FAILED_CLASSIFICATION", 10)

    assert worker.get_next_notification_id(
        max_age_seconds=120,
        session_factory=sessions,
    ) is None


def test_processes_one_notification():
    sessions = make_session_factory()

    notification_id = add_notification(
        sessions, "RECEIVED", 10
    )

    processor = Mock(
        return_value=SimpleNamespace(
            notification_id=notification_id,
            status="CLASSIFIED_DRY_RUN",
        )
    )

    result = worker.process_next_notification(
        session_factory=sessions,
        processor=processor,
    )

    assert result.status == "CLASSIFIED_DRY_RUN"
    processor.assert_called_once_with(notification_id)


def test_processor_failure_does_not_crash_poller():
    sessions = make_session_factory()

    add_notification(sessions, "RECEIVED", 10)

    processor = Mock(
        side_effect=RuntimeError("Simulated OpenAI failure")
    )

    result = worker.process_next_notification(
        session_factory=sessions,
        processor=processor,
    )

    assert result is None
    processor.assert_called_once()


def test_no_pending_notification_does_not_call_processor():
    sessions = make_session_factory()

    processor = Mock()

    result = worker.process_next_notification(
        session_factory=sessions,
        processor=processor,
    )

    assert result is None
    processor.assert_not_called()

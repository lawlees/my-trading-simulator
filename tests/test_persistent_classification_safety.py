
"""Safety tests for the persistent dry-run classifier."""

import threading
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

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


def add_notification(session_factory, status="RECEIVED"):
    with session_factory() as session:
        item = IncomingNotification(
            source="MANUAL_ENTRY",
            idempotency_key=f"safety-{id(session)}",
            message_text="Watching SPY support. No position taken.",
            received_at=datetime.now(timezone.utc),
            processing_status=status,
        )
        session.add(item)
        session.commit()
        return item.id


def test_startup_watermark_excludes_existing_notifications():
    sessions = make_session_factory()

    old_id = add_notification(sessions)

    watermark = worker.get_startup_watermark(
        session_factory=sessions,
    )

    assert watermark == old_id

    # A notification created before startup is excluded.
    assert worker.get_next_notification_id(
        min_notification_id=watermark,
        session_factory=sessions,
    ) is None

    new_id = add_notification(sessions)

    # A newly received notification is eligible.
    assert worker.get_next_notification_id(
        min_notification_id=watermark,
        session_factory=sessions,
    ) == new_id


def test_unclaimed_processor_failure_marks_notification_failed():
    sessions = make_session_factory()
    notification_id = add_notification(sessions)

    processor = Mock(
        side_effect=RuntimeError("Simulated processor failure")
    )

    result = worker.process_next_notification(
        session_factory=sessions,
        processor=processor,
    )

    assert result is None
    processor.assert_called_once_with(notification_id)

    with sessions() as session:
        item = session.get(IncomingNotification, notification_id)

        assert item.processing_status == "FAILED_CLASSIFICATION"
        assert "UnexpectedWorkerError" in item.processing_error

    # Failed notifications must not be automatically retried.
    assert worker.get_next_notification_id(
        session_factory=sessions,
    ) is None


def test_failure_fallback_does_not_overwrite_processing_state():
    sessions = make_session_factory()
    notification_id = add_notification(
        sessions,
        status="PROCESSING",
    )

    worker.mark_unclaimed_failure(
        notification_id,
        session_factory=sessions,
    )

    with sessions() as session:
        item = session.get(IncomingNotification, notification_id)
        assert item.processing_status == "PROCESSING"


def test_worker_uses_startup_watermark():
    sessions = make_session_factory()
    old_id = add_notification(sessions)

    stop_event = threading.Event()
    observed_watermarks = []

    def fake_process_next_notification(**kwargs):
        observed_watermarks.append(
            kwargs["min_notification_id"]
        )
        stop_event.set()
        return SimpleNamespace(
            notification_id=old_id,
            status="CLASSIFIED_DRY_RUN",
        )

    with patch.object(
        worker,
        "process_next_notification",
        side_effect=fake_process_next_notification,
    ):
        worker.run_forever(
            poll_seconds=0.01,
            stop_event=stop_event,
            session_factory=sessions,
        )

    assert observed_watermarks == [old_id]

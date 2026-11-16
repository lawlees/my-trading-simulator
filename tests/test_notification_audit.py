"""Offline operational audit tests; never mutate real notification database."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from my_trading_simulator.database.models import IncomingNotification, NotificationClassification
from my_trading_simulator.observability.notification_audit import summarize_notifications


@pytest.fixture
def sessions(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'audit.db'}")
    IncomingNotification.__table__.create(engine)
    NotificationClassification.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


def test_audit_reports_pending_and_stuck_without_message_data(sessions):
    now = datetime(2026, 11, 15, tzinfo=timezone.utc)
    with sessions.begin() as session:
        session.add_all([
            IncomingNotification(source="MANUAL_ENTRY", message_text="do not echo private text",
                                 idempotency_key="audit-pending", received_at=now, processing_status="RECEIVED"),
            IncomingNotification(source="MANUAL_ENTRY", message_text="private text",
                                 idempotency_key="audit-stuck", received_at=now - timedelta(minutes=5), processing_status="PROCESSING"),
        ])
    report = summarize_notifications(session_factory=sessions, now=now)
    assert report["notification_statuses"] == {"RECEIVED": 1, "PROCESSING": 1}
    assert len(report["pending_received_ids"]) == 1
    assert len(report["possible_stuck_processing_ids"]) == 1
    assert report["execution_authorized_classifications"] == 0
    assert "private text" not in str(report)
    with sessions() as session:
        assert session.query(IncomingNotification).count() == 2


def test_audit_detects_unexpected_execution_authorization(sessions):
    with sessions.begin() as session:
        item = IncomingNotification(source="MANUAL_ENTRY", message_text="test",
                                    idempotency_key="audit-classification", processing_status="CLASSIFIED_DRY_RUN")
        session.add(item)
        session.flush()
        session.add(NotificationClassification(
            notification_id=item.id, action="BUY", symbol="SPY", option_type="CALL",
            parser_is_actionable=True, execution_allowed=True,
            model_message_id="inbox-audit", reason="test",
        ))
    report = summarize_notifications(session_factory=sessions)
    assert report["execution_authorized_classifications"] == 1


def test_audit_rejects_invalid_timeout(sessions):
    with pytest.raises(ValueError):
        summarize_notifications(session_factory=sessions, processing_timeout_seconds=0)

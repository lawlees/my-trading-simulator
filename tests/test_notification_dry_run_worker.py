"""Dry-run worker regression tests; no real OpenAI, Schwab, or Discord requests."""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from my_trading_simulator.database.models import (
    IncomingNotification, NotificationClassification,
)
from my_trading_simulator.ingestion.notification_dry_run_worker import (
    process_notification,
)
from my_trading_simulator.signals.models import (
    OptionType, SignalAction, TradingSignal,
)


@pytest.fixture
def db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'worker.db'}")
    IncomingNotification.__table__.create(eng)
    NotificationClassification.__table__.create(eng)
    factory = sessionmaker(bind=eng, expire_on_commit=False)
    yield factory
    eng.dispose()


def create_notification(db, text, status="RECEIVED"):
    with db() as session:
        item = IncomingNotification(
            source="IPHONE_NOTIFICATION",
            idempotency_key=uuid4().hex,
            message_text=text,
            processing_status=status,
        )
        session.add(item)
        session.commit()
        return item.id


def mock_buy(**kwargs):
    return TradingSignal(
        message_id=kwargs["message_id"], raw_message=kwargs["message_text"],
        action=SignalAction.BUY, symbol="SPY", option_type=OptionType.CALL,
        is_actionable=True, reason="Explicit entry",
    )


def test_test_message_skipped_without_llm(db):
    n = create_notification(db, "Casey TEST ONLY taking SPY calls")
    def forbidden(**kwargs):
        raise AssertionError("LLM called for test notification")
    result = process_notification(n, session_factory=db, parser=forbidden)
    assert result.status == "SKIPPED_TEST"
    with db() as session:
        assert session.get(IncomingNotification, n).processing_status == "SKIPPED_TEST"
        assert session.scalar(select(func.count()).select_from(NotificationClassification)) == 0


def test_classification_saved_with_execution_disabled(db):
    n = create_notification(db, "Casey taking SPY calls here")
    result = process_notification(n, session_factory=db, parser=mock_buy)
    assert result.status == "CLASSIFIED_DRY_RUN"
    with db() as session:
        classification = session.scalar(select(NotificationClassification))
        assert classification.notification_id == n
        assert classification.action == "BUY"
        assert classification.symbol == "SPY"
        assert classification.parser_is_actionable is True
        assert classification.execution_allowed is False
        assert classification.model_message_id == f"inbox-{n}"
        assert session.get(IncomingNotification, n).processing_status == "CLASSIFIED_DRY_RUN"


def test_second_processing_does_not_call_parser(db):
    n = create_notification(db, "Casey taking SPY calls here")
    process_notification(n, session_factory=db, parser=mock_buy)
    def forbidden(**kwargs):
        raise AssertionError("Repeated parser invocation")
    result = process_notification(n, session_factory=db, parser=forbidden)
    assert result.status == "CLASSIFIED_DRY_RUN"
    with db() as session:
        assert session.scalar(select(func.count()).select_from(NotificationClassification)) == 1


def test_possible_duplicate_on_hold(db):
    n = create_notification(db, "Casey taking SPY calls here", "POSSIBLE_DUPLICATE")
    def forbidden(**kwargs):
        raise AssertionError("Possible duplicate parsed")
    result = process_notification(n, session_factory=db, parser=forbidden)
    assert result.status == "POSSIBLE_DUPLICATE"


def test_failure_is_recorded_and_not_retried(db):
    n = create_notification(db, "Casey taking SPY calls here")
    def failing(**kwargs):
        raise ConnectionError("simulated failure")
    with pytest.raises(ConnectionError):
        process_notification(n, session_factory=db, parser=failing)
    with db() as session:
        item = session.get(IncomingNotification, n)
        assert item.processing_status == "FAILED_CLASSIFICATION"
        assert "ConnectionError" in item.processing_error
    result = process_notification(n, session_factory=db, parser=mock_buy)
    assert result.status == "FAILED_CLASSIFICATION"


def test_missing_id(db):
    result = process_notification(999, session_factory=db, parser=mock_buy)
    assert result.status == "NOT_FOUND"

"""Exact contract details survive a dry-run classification and migration."""

from decimal import Decimal

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from my_trading_simulator.database.models import (
    Base, IncomingNotification, NotificationClassification,
)
from my_trading_simulator.database.migrate_classification_contracts import migrate
from my_trading_simulator.ingestion.notification_dry_run_worker import process_notification
from my_trading_simulator.signals.models import OptionType, SignalAction, TradingSignal


def make_db():
    db_engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(db_engine)
    return db_engine, sessionmaker(bind=db_engine)


def test_dry_run_persists_explicit_strike_without_execution():
    db_engine, sessions = make_db()
    with sessions() as session:
        notification = IncomingNotification(
            source="MANUAL_ENTRY", idempotency_key="strike-example",
            message_text="SPY CALL entry strike 670", processing_status="RECEIVED",
        )
        session.add(notification)
        session.commit()
        nid = notification.id

    signal = TradingSignal(
        message_id=f"inbox-{nid}", raw_message="SPY CALL entry strike 670",
        action=SignalAction.BUY, symbol="SPY", option_type=OptionType.CALL,
        strike_price=Decimal("670"), is_actionable=True, reason="Explicit call",
    )
    result = process_notification(nid, session_factory=sessions, parser=lambda **_: signal)
    assert result.status == "CLASSIFIED_DRY_RUN"
    with sessions() as session:
        classification = session.scalar(
            select(NotificationClassification).where(
                NotificationClassification.notification_id == nid
            )
        )
        assert classification.strike_price == Decimal("670")
        assert classification.contract_symbol is None
        assert classification.execution_allowed is False


def test_dry_run_persists_exact_contract_without_execution():
    _, sessions = make_db()
    with sessions() as session:
        item = IncomingNotification(
            source="MANUAL_ENTRY", idempotency_key="occ-example",
            message_text="Buy specified SPY contract", processing_status="RECEIVED",
        )
        session.add(item)
        session.commit()
        nid = item.id
    option = "SPY 261116C00670000"
    signal = TradingSignal(
        message_id=f"inbox-{nid}", raw_message="Buy specified SPY contract",
        action=SignalAction.BUY, symbol="SPY", option_type=OptionType.CALL,
        contract_symbol=option, is_actionable=True, reason="Explicit OCC contract",
    )
    result = process_notification(nid, session_factory=sessions, parser=lambda **_: signal)
    assert result.status == "CLASSIFIED_DRY_RUN"
    with sessions() as session:
        classification = session.scalar(select(NotificationClassification))
        assert classification.contract_symbol == option
        assert classification.strike_price is None
        assert not classification.execution_allowed


def test_migration_on_legacy_schema_is_idempotent_and_preserves_data():
    db_engine = create_engine("sqlite+pysqlite:///:memory:")
    with db_engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE notification_classifications (id INTEGER PRIMARY KEY, action VARCHAR(30))")
        conn.exec_driver_sql("INSERT INTO notification_classifications (id, action) VALUES (1, 'IGNORE')")
    assert migrate(db_engine) == ("strike_price", "contract_symbol")
    assert migrate(db_engine) == ()
    columns = {entry["name"] for entry in inspect(db_engine).get_columns("notification_classifications")}
    assert {"strike_price", "contract_symbol"}.issubset(columns)
    with db_engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT action FROM notification_classifications WHERE id=1").scalar() == "IGNORE"


def test_migration_rejects_missing_schema():
    db_engine = create_engine("sqlite+pysqlite:///:memory:")
    import pytest
    with pytest.raises(RuntimeError, match="missing"):
        migrate(db_engine)

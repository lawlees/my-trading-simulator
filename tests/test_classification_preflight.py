"""Preflight never changes the account or executes a trade."""
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from my_trading_simulator.database.models import (
    Base, NotificationClassification, OptionPosition, PaperAccount, IncomingNotification,
)
from my_trading_simulator.execution.classification_preflight import review_classification


def setup():
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions.begin() as session:
        session.add(PaperAccount(name="test", initial_balance=Decimal("7000"), cash_balance=Decimal("7000")))
        session.add(IncomingNotification(source="TEST", idempotency_key="fixture", message_text="casey", processing_status="CLASSIFIED_DRY_RUN"))
    with sessions.begin() as session:
        account_id = session.scalar(select(PaperAccount.id))
        notification_id = session.scalar(select(IncomingNotification.id))
        item = NotificationClassification(notification_id=notification_id, model_message_id="inbox-1", action="BUY", symbol="SPY", option_type="CALL", parser_is_actionable=True, execution_allowed=False, reason="fixture")
        session.add(item)
        session.flush()
        classification_id = item.id
    return sessions, account_id, classification_id


def test_buy_is_review_only_and_never_mutates_database():
    sessions, account_id, cid = setup()
    with sessions() as session:
        before = session.get(PaperAccount, account_id).cash_balance
        result = review_classification(session, classification_id=cid, account_id=account_id)
        assert result.status == "REVIEW_ONLY"
        assert result.execution_allowed is False
        assert session.get(PaperAccount, account_id).cash_balance == before
        assert session.scalar(select(OptionPosition.id)) is None


def test_buy_blocked_when_runner_remains_open():
    sessions, account_id, cid = setup()
    from datetime import date
    with sessions.begin() as session:
        session.add(OptionPosition(account_id=account_id, symbol="QQQ", option_type="PUT", strike_price=Decimal("400"), expiration_date=date(2026, 11, 16), quantity=2, remaining_quantity=1, entry_price=Decimal("1"), status="OPEN", entry_type="INITIAL"))
    with sessions() as session:
        result = review_classification(session, classification_id=cid, account_id=account_id)
        assert result.status == "BLOCKED"
        assert "position remains open" in result.reason


def test_manually_set_execution_flag_is_not_trusted():
    sessions, account_id, cid = setup()
    with sessions.begin() as session:
        session.get(NotificationClassification, cid).execution_allowed = True
    with sessions() as session:
        result = review_classification(session, classification_id=cid, account_id=account_id)
        assert result.status == "BLOCKED"
        assert not result.execution_allowed


def test_add_never_executes_without_trade_context():
    sessions, account_id, cid = setup()
    with sessions.begin() as session:
        session.get(NotificationClassification, cid).action = "ADD"
    with sessions() as session:
        result = review_classification(session, classification_id=cid, account_id=account_id)
        assert result.status == "REVIEW_ONLY"
        assert not result.execution_allowed


def test_unknown_classification_is_blocked():
    sessions, account_id, _ = setup()
    with sessions() as session:
        result = review_classification(session, classification_id=99999, account_id=account_id)
        assert result.status == "BLOCKED"

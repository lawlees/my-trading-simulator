"""Mocked Discord publisher tests: no outgoing HTTP and no production SQLite."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from my_trading_simulator.database.models import Base, PaperAccount, TradeEvent
from my_trading_simulator.discord.discord_outbox_publisher import (
    DefiniteDeliveryFailure, UncertainDelivery, publish_one_pending_event,
)

WEBHOOK = "https://discord.com/api/webhooks/123456/test-secret"


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'outbox.db'}", connect_args={"timeout": 10})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as s:
        account = PaperAccount(name="outbox-test", initial_balance=Decimal("7000"), cash_balance=Decimal("7000"))
        s.add(account)
        s.flush()
        s.add(TradeEvent(account_id=account.id, event_type="BUY_FILLED", message="PAPER BUY 4 SPY CALL", payload="{}", delivery_status="PENDING"))
    yield sessions
    engine.dispose()


def get_event(db):
    with db() as s:
        return s.scalar(select(TradeEvent))


def test_success_commits_discord_message_id(db):
    seen = []
    result = publish_one_pending_event(session_factory=db, webhook_url=WEBHOOK, sender=lambda u, content: seen.append(content) or "987654321")
    assert result.status == "SENT"
    assert len(seen) == 1 and "event #1" in seen[0]
    event = get_event(db)
    assert event.delivery_status == "SENT"
    assert event.discord_message_id == "987654321"
    assert event.delivery_attempts == 1
    assert event.delivered_at is not None


def test_repeat_does_not_duplicate(db):
    send = lambda u, content: "123456"
    assert publish_one_pending_event(session_factory=db, webhook_url=WEBHOOK, sender=send).status == "SENT"
    assert publish_one_pending_event(session_factory=db, webhook_url=WEBHOOK, sender=send).status == "EMPTY"
    assert get_event(db).delivery_attempts == 1


def test_known_rejection_is_failed_and_not_retried(db):
    def fail(u, content):
        raise DefiniteDeliveryFailure("Discord HTTP 429")
    assert publish_one_pending_event(session_factory=db, webhook_url=WEBHOOK, sender=fail).status == "FAILED"
    assert get_event(db).delivery_status == "FAILED"
    assert publish_one_pending_event(session_factory=db, webhook_url=WEBHOOK, sender=fail).status == "EMPTY"


def test_uncertain_delivery_is_not_retried(db):
    def ambiguous(u, content):
        raise UncertainDelivery("Lost response after send")
    assert publish_one_pending_event(session_factory=db, webhook_url=WEBHOOK, sender=ambiguous).status == "UNKNOWN"
    assert publish_one_pending_event(session_factory=db, webhook_url=WEBHOOK, sender=ambiguous).status == "EMPTY"
    assert get_event(db).discord_message_id is None


def test_missing_webhook_does_not_claim_event(db):
    with pytest.raises(ValueError, match="webhook URL"):
        publish_one_pending_event(session_factory=db, webhook_url="http://bad.example/api/webhooks/abc/def", sender=lambda u, c: "1")
    assert get_event(db).delivery_status == "PENDING"


def test_concurrent_publishers_claim_once(db):
    gate = Barrier(2)
    calls = []
    def send(u, c):
        calls.append(c)
        return "10000"
    def run():
        gate.wait(timeout=5)
        return publish_one_pending_event(session_factory=db, webhook_url=WEBHOOK, sender=send).status
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [f.result() for f in [pool.submit(run), pool.submit(run)]]
    assert sorted(outcomes) == ["EMPTY", "SENT"]
    assert len(calls) == 1

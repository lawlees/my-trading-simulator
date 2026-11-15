"""Tests for one-cycle monitoring with an isolated SQLite database."""
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from my_trading_simulator.database.models import Base, OptionPosition, PaperAccount
from my_trading_simulator.execution import paper_broker
from my_trading_simulator.execution.stop_monitor_worker import run_monitor_cycle

NOW = datetime(2026, 11, 13, 16, 0, tzinfo=timezone.utc)
OCC = "SPY   261113C00600000"


@pytest.fixture
def database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'monitor_cycle.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(paper_broker, "SessionLocal", sessions)
    with sessions.begin() as session:
        account = PaperAccount(name="Worker Tests", initial_balance=Decimal("7000"), cash_balance=Decimal("7000"))
        session.add(account)
        session.flush()
        account_id = account.id
    yield sessions, account_id
    engine.dispose()


def create_position(sessions, account_id, *, occ=OCC, status="OPEN", stop="0.50"):
    with sessions.begin() as session:
        p = OptionPosition(
            account_id=account_id, symbol="SPY", option_type="CALL",
            option_symbol=occ, strike_price=Decimal("600"),
            expiration_date=date(2026, 11, 13), quantity=1,
            remaining_quantity=1 if status == "OPEN" else 0,
            entry_price=Decimal("1.00"), stop_price=Decimal(stop),
            status=status, entry_type="INITIAL",
        )
        session.add(p)
        session.flush()
        return p.id


def quote_client(*, bid="0.40", ask="0.42", timestamp=None):
    calls = []
    def get_option_quote(symbol):
        calls.append(symbol)
        return {"quote": {"bidPrice": float(bid), "askPrice": float(ask),
                          "quoteTime": timestamp if timestamp is not None else int(NOW.timestamp() * 1000)}}
    return SimpleNamespace(get_option_quote=get_option_quote, calls=calls)


def test_empty_cycle_does_not_request_quotes(database):
    sessions, _ = database
    client = quote_client()
    result = run_monitor_cycle(client, session_factory=sessions, now=NOW)
    assert result.checked == 0
    assert result.results == ()
    assert client.calls == []


def test_trigger_closes_only_open_position(database):
    sessions, account_id = database
    open_id = create_position(sessions, account_id)
    closed_id = create_position(sessions, account_id, status="CLOSED")
    client = quote_client()
    result = run_monitor_cycle(client, session_factory=sessions, now=NOW)
    assert result.checked == 1
    assert [(r.position_id, r.status) for r in result.results] == [(open_id, "STOP_FILLED")]
    assert client.calls == [OCC]
    with sessions() as session:
        assert session.get(OptionPosition, open_id).remaining_quantity == 0
        assert session.get(OptionPosition, closed_id).status == "CLOSED"


def test_stale_quote_is_alert_and_does_not_sell(database):
    sessions, account_id = database
    pid = create_position(sessions, account_id)
    client = quote_client(timestamp=int(NOW.timestamp()*1000)-15000)
    result = run_monitor_cycle(client, session_factory=sessions, now=NOW)
    assert result.checked == 1
    assert len(result.alerts) == 1
    with sessions() as session:
        assert session.get(OptionPosition, pid).remaining_quantity == 1


def test_one_position_error_does_not_interrupt_others(database):
    sessions, account_id = database
    bad_id = create_position(sessions, account_id, occ=None)
    good_id = create_position(sessions, account_id)
    client = quote_client(bid="0.70", ask="0.72")
    result = run_monitor_cycle(client, session_factory=sessions, now=NOW)
    assert [(r.position_id, r.status) for r in result.results] == [
        (bad_id, "ALERT"), (good_id, "NO_EXIT")]
    assert len(result.alerts) == 1
    assert client.calls == [OCC]


def test_cycle_after_stop_does_not_repeat_sell(database):
    sessions, account_id = database
    create_position(sessions, account_id)
    client = quote_client()
    assert run_monitor_cycle(client, session_factory=sessions, now=NOW).checked == 1
    assert run_monitor_cycle(client, session_factory=sessions, now=NOW).checked == 0
    assert client.calls == [OCC]

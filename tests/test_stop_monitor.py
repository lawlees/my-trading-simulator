"""No Schwab network requests; every test uses a temporary SQLite database."""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from my_trading_simulator.database.models import Base, PaperAccount, OptionPosition, TradeFill
from my_trading_simulator.execution import paper_broker
from my_trading_simulator.execution.stop_monitor import monitor_position_once

NOW = datetime(2026, 11, 13, 16, 0, tzinfo=timezone.utc)
OCC = "SPY   261113C00600000"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'monitor.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(paper_broker, "SessionLocal", sessions)
    with sessions.begin() as session:
        account = PaperAccount(name="monitor test", initial_balance=Decimal("7000"), cash_balance=Decimal("7000"))
        session.add(account)
        session.flush()
        account_id = account.id
    with sessions.begin() as session:
        position = OptionPosition(
            account_id=account_id, symbol="SPY", option_type="CALL", option_symbol=OCC,
            strike_price=Decimal("600"), expiration_date=NOW.date(), quantity=2,
            remaining_quantity=2, entry_price=Decimal("1.00"), stop_price=Decimal("0.50"),
            status="OPEN", entry_type="INITIAL",
        )
        session.add(position)
        session.flush()
        pid = position.id
    yield sessions, pid
    engine.dispose()


def client(bid="0.40", ask="0.42", *, age_ms=0):
    calls = []
    def get(symbol):
        calls.append(symbol)
        return {"quote": {"bidPrice": float(bid), "askPrice": float(ask),
                          "quoteTime": int(NOW.timestamp() * 1000) - age_ms}}
    return SimpleNamespace(get_option_quote=get, calls=calls)


def check(setup, quote_client, *, now=NOW):
    sessions, pid = setup
    return monitor_position_once(pid, quote_client, now=now, session_factory=sessions)


def test_triggered_stop_closes_position_and_records_fill(setup):
    quote_client = client()
    result = check(setup, quote_client)
    assert result.status == "STOP_FILLED"
    assert quote_client.calls == [OCC]
    sessions, pid = setup
    with sessions() as session:
        p = session.get(OptionPosition, pid)
        assert p.remaining_quantity == 0
        assert p.close_reason == "STOP"
        assert len(session.scalars(select(TradeFill).where(TradeFill.position_id == pid, TradeFill.side == "SELL")).all()) == 1


def test_bid_above_stop_does_not_exit(setup):
    result = check(setup, client("0.70", "0.72"))
    assert result.status == "NO_EXIT"
    sessions, pid = setup
    with sessions() as session:
        assert session.get(OptionPosition, pid).remaining_quantity == 2


def test_stale_quote_does_not_exit(setup):
    result = check(setup, client(age_ms=15000))
    assert result.status == "ALERT"
    sessions, pid = setup
    with sessions() as session:
        assert session.get(OptionPosition, pid).remaining_quantity == 2


def test_outside_hours_never_requests_quote(setup):
    quote_client = client()
    result = check(setup, quote_client, now=datetime(2026, 11, 14, 16, tzinfo=timezone.utc))
    assert result.status == "SKIPPED"
    assert quote_client.calls == []


def test_no_duplicate_stop_execution(setup):
    quote_client = client()
    assert check(setup, quote_client).status == "STOP_FILLED"
    assert check(setup, quote_client).status == "SKIPPED"

"""Transactional guard: a stopped initial entry cannot become a second BUY."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
from threading import Barrier
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from my_trading_simulator.database.models import (
    Base, PaperAccount, TradeIdea, OptionPosition, TradeFill,
)
from my_trading_simulator.execution import paper_broker


@pytest.fixture
def account(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'paper_guard.db'}",
        connect_args={"timeout": 5},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(paper_broker, "SessionLocal", sessions)
    with sessions.begin() as s:
        a = PaperAccount(name="test", initial_balance=Decimal("7000"),
                         cash_balance=Decimal("7000"))
        s.add(a)
        s.flush()
        aid = a.id
    yield aid, sessions
    engine.dispose()


def do_buy(aid):
    return paper_broker.buy_option(
        account_id=aid, symbol="SPY", option_type="CALL",
        strike_price=Decimal("600"),
        expiration_date=datetime.now(ZoneInfo("America/New_York")).date(),
        quantity=1, fill_price=Decimal("1.00"),
        stop_price=Decimal("0.60"),
    )


def add_idea(s, aid, status="ACTIVE"):
    s.add(TradeIdea(
        account_id=aid, symbol="SPY", option_type="CALL",
        size_type="NORMAL", initial_allocation=Decimal("400"),
        initial_risk_limit=Decimal("150"), additions_used=0,
        status=status,
    ))


def test_active_idea_without_position_blocks_fresh_buy(account):
    aid, sessions = account
    with sessions.begin() as s:
        add_idea(s, aid)
    with pytest.raises(ValueError, match="active trade idea"):
        do_buy(aid)
    with sessions() as s:
        assert s.get(PaperAccount, aid).cash_balance == Decimal("7000")
        assert s.scalar(select(OptionPosition.id)) is None
        assert s.scalar(select(TradeFill.id)) is None
        assert len(s.scalars(select(TradeIdea)).all()) == 1


def test_closed_idea_without_position_allows_new_buy(account):
    aid, sessions = account
    with sessions.begin() as s:
        add_idea(s, aid, status="CLOSED")
    position_id = do_buy(aid)
    with sessions() as s:
        assert s.get(OptionPosition, position_id).status == "OPEN"
        assert len(s.scalars(select(TradeIdea)).all()) == 2


def test_concurrent_initial_buys_admit_only_one(account):
    aid, sessions = account
    gate = Barrier(2)

    def attempt():
        gate.wait(timeout=5)
        try:
            do_buy(aid)
            return "OK"
        except ValueError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert results.count("OK") == 1
    assert len(results) == 2
    assert any("Another option position remains open" in r for r in results)
    with sessions() as s:
        assert len(s.scalars(select(OptionPosition)).all()) == 1
        assert len(s.scalars(select(TradeFill)).all()) == 1
        assert len(s.scalars(select(TradeIdea)).all()) == 1

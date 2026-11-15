from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo
import json
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from my_trading_simulator.database.models import Base, PaperAccount, OptionPosition, TradeEvent, TradeFill, TradeIdea
from my_trading_simulator.execution import paper_broker
from my_trading_simulator.strategy import lifecycle

TODAY = datetime.now(ZoneInfo('America/New_York')).date()

@pytest.fixture
def ctx(tmp_path, monkeypatch):
    eng=create_engine(f"sqlite:///{tmp_path/'trades.db'}")
    Base.metadata.create_all(eng)
    sessions=sessionmaker(bind=eng, expire_on_commit=False)
    monkeypatch.setattr(paper_broker, 'SessionLocal', sessions)
    monkeypatch.setattr(lifecycle, 'SessionLocal', sessions)
    with sessions.begin() as s:
        a=PaperAccount(name='outbox', initial_balance=Decimal('7000'),cash_balance=Decimal('7000'))
        s.add(a); s.flush(); aid=a.id
    yield aid,sessions
    eng.dispose()

def buy(aid, **kw):
    return paper_broker.buy_option(aid,'SPY','CALL',Decimal('600'),TODAY,4,Decimal('1.00'),Decimal('0.65'),**kw)

def events(sessions):
    with sessions() as s:
        return [(e.event_type,e.delivery_status,e.position_id,json.loads(e.payload)) for e in s.scalars(select(TradeEvent).order_by(TradeEvent.id)).all()]

def test_buy_event_atomic(ctx):
    aid,sessions=ctx; pid=buy(aid)
    assert [(t,st,p) for t,st,p,_ in events(sessions)] == [('BUY_FILLED','PENDING',pid)]
    with pytest.raises(ValueError): buy(aid)
    assert len(events(sessions)) == 1

def test_add_event_atomic(ctx):
    aid,sessions=ctx; pid=buy(aid)
    with sessions() as s:
        idea=s.get(OptionPosition,pid).trade_idea_id
    paper_broker.add_option(idea,Decimal('600'),TODAY,2,Decimal('0.50'),Decimal('0.20'))
    assert [v[0] for v in events(sessions)] == ['BUY_FILLED','ADD_FILLED']

def test_stop_event_once(ctx):
    aid,sessions=ctx; pid=buy(aid)
    assert paper_broker.process_option_stop(pid, Decimal('0.60')) is True
    assert paper_broker.process_option_stop(pid, Decimal('0.50')) is False
    assert [v[0] for v in events(sessions)] == ['BUY_FILLED','STOP_FILLED']
    with sessions() as s:
        assert s.get(OptionPosition,pid).close_reason=='STOP'

def test_manual_partial_and_close(ctx):
    aid,sessions=ctx; pid=buy(aid)
    paper_broker.sell_option(pid,2,Decimal('1.20'))
    paper_broker.sell_option(pid,2,Decimal('1.30'))
    assert [v[0] for v in events(sessions)] == ['BUY_FILLED','PARTIAL_SELL','POSITION_CLOSED']

def test_lifecycle_profit_take_event(ctx):
    aid,sessions=ctx; pid=buy(aid)
    assert lifecycle.claim_profit_take(pid)
    lifecycle.complete_profit_take(pid,Decimal('1.50'))
    assert [v[0] for v in events(sessions)] == ['BUY_FILLED','PROFIT_TAKEN']
    assert events(sessions)[-1][-1]['remaining_quantity'] == 1

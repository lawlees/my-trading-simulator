from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from my_trading_simulator.signals.models import SignalAction, TradingSignal
from my_trading_simulator.signals.validator import validate_signal
from my_trading_simulator.database.models import Base, PaperAccount, OptionPosition, TradeIdea
from my_trading_simulator.execution import paper_broker


def test_validator_copy_and_ignore():
    signal = TradingSignal(message_id="1", raw_message="x", action=SignalAction.BUY,
                           symbol=" spy ", option_type="CALL", is_actionable=True, reason="x")
    validated = validate_signal(signal)
    assert validated.is_actionable and validated.symbol == "SPY"
    assert signal.symbol == " spy "


@pytest.fixture
def account(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'audit.db'}", connect_args={"timeout": 5})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(paper_broker, "SessionLocal", factory)
    with factory.begin() as s:
        a = PaperAccount(name="audit", initial_balance=Decimal("7000"), cash_balance=Decimal("7000"))
        s.add(a)
        s.flush()
        aid = a.id
    yield aid, factory
    engine.dispose()


def entry(aid, *, symbol="SPY", qty=2, fill="1.00", stop="0.40", **kwargs):
    return paper_broker.buy_option(account_id=aid, symbol=symbol, option_type="CALL",
        strike_price=Decimal("600"),
        expiration_date=datetime.now(ZoneInfo("America/New_York")).date(),
        quantity=qty, fill_price=Decimal(fill), stop_price=Decimal(stop), **kwargs)


def test_position_limit_including_runner(account):
    aid, sessions = account
    pos = entry(aid)
    with pytest.raises(ValueError, match="position remains open"):
        entry(aid, symbol="QQQ")
    paper_broker.sell_option(pos, 1, Decimal("1.20"))
    with pytest.raises(ValueError, match="position remains open"):
        entry(aid, symbol="IWM")


def test_add_once_and_stop_reentry(account):
    aid, sessions = account
    pos = entry(aid)
    with sessions() as s:
        p = s.get(OptionPosition, pos)
        idea_id = p.trade_idea_id
        assert p.stop_price == Decimal("0.40")
    added = paper_broker.add_option(idea_id, Decimal("600"),
        datetime.now(ZoneInfo("America/New_York")).date(),
        1, Decimal("1.00"), Decimal("0.40"))
    assert added == pos
    with pytest.raises(ValueError, match="ADD limit"):
        paper_broker.add_option(idea_id, Decimal("600"),
            datetime.now(ZoneInfo("America/New_York")).date(),
            1, Decimal("1.00"), Decimal("0.40"))
    assert paper_broker.process_option_stop(pos, Decimal("0.30"))
    with sessions() as s:
        assert s.get(OptionPosition, pos).close_reason == "STOP"


def test_stop_only_on_trigger(account):
    aid, sessions = account
    pos = entry(aid)
    assert not paper_broker.process_option_stop(pos, Decimal("0.80"))
    assert paper_broker.process_option_stop(pos, Decimal("0.35"))
    assert not paper_broker.process_option_stop(pos, Decimal("0.35"))
    with sessions() as s:
        assert s.get(OptionPosition, pos).status == "CLOSED"


def test_stopped_out_idea_can_reenter_once(account):
    aid, sessions = account
    pos = entry(aid)
    with sessions() as s:
        idea_id = s.get(OptionPosition, pos).trade_idea_id
    assert paper_broker.process_option_stop(pos, Decimal("0.30"))
    new_pos = paper_broker.add_option(
        idea_id, Decimal("600"), datetime.now(ZoneInfo("America/New_York")).date(),
        1, Decimal("1.00"), Decimal("0.40"),
    )
    assert new_pos != pos
    with sessions() as s:
        replacement = s.get(OptionPosition, new_pos)
        assert replacement.entry_type == "ADD"
        assert replacement.trade_idea_id == idea_id
    with pytest.raises(ValueError, match="position remains open"):
        entry(aid, symbol="IWM")

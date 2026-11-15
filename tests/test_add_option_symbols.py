"""Exact-contract ADD safety tests. Uses isolated temporary SQLite databases."""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from my_trading_simulator.database.models import Base, OptionPosition, PaperAccount, TradeIdea
from my_trading_simulator.execution import paper_broker


@pytest.fixture
def paper_account(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'add_symbols.db'}",
        connect_args={"timeout": 10},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(paper_broker, "SessionLocal", sessions)
    with sessions.begin() as session:
        account = PaperAccount(
            name="ADD Symbol Test",
            initial_balance=Decimal("7000"),
            cash_balance=Decimal("7000"),
        )
        session.add(account)
        session.flush()
        account_id = account.id
    yield account_id, sessions
    engine.dispose()


def today_and_symbol(strike=600):
    today = datetime.now(ZoneInfo("America/New_York")).date()
    occ = f"SPY   {today:%y%m%d}C{strike * 1000:08d}"
    return today, occ


def open_initial(account_id, *, option_symbol):
    today, _ = today_and_symbol()
    return paper_broker.buy_option(
        account_id=account_id,
        symbol="SPY",
        option_type="CALL",
        strike_price=Decimal("600"),
        expiration_date=today,
        quantity=2,
        fill_price=Decimal("1.00"),
        stop_price=Decimal("0.40"),
        option_symbol=option_symbol,
    )


def get_idea_id(sessions, position_id):
    with sessions() as session:
        return session.get(OptionPosition, position_id).trade_idea_id


def add(idea_id, *, option_symbol, strike=600):
    today, _ = today_and_symbol()
    return paper_broker.add_option(
        trade_idea_id=idea_id,
        strike_price=Decimal(str(strike)),
        expiration_date=today,
        quantity=1,
        fill_price=Decimal("1.00"),
        stop_price=Decimal("0.40"),
        option_symbol=option_symbol,
    )


def test_add_same_exact_symbol_succeeds(paper_account):
    account_id, sessions = paper_account
    _, occ = today_and_symbol()
    position_id = open_initial(account_id, option_symbol=occ)
    idea_id = get_idea_id(sessions, position_id)

    assert add(idea_id, option_symbol=occ) == position_id
    with sessions() as session:
        position = session.get(OptionPosition, position_id)
        assert position.option_symbol == occ
        assert position.quantity == 3
        assert position.remaining_quantity == 3
        assert session.get(TradeIdea, idea_id).additions_used == 1


def test_add_missing_symbol_rejected_for_verified_position(paper_account):
    account_id, sessions = paper_account
    _, occ = today_and_symbol()
    position_id = open_initial(account_id, option_symbol=occ)
    idea_id = get_idea_id(sessions, position_id)

    with pytest.raises(ValueError, match="exact option symbol"):
        add(idea_id, option_symbol=None)

    with sessions() as session:
        assert session.get(TradeIdea, idea_id).additions_used == 0
        assert session.get(OptionPosition, position_id).quantity == 2


def test_add_wrong_occ_symbol_rejected(paper_account):
    account_id, sessions = paper_account
    today, occ = today_and_symbol()
    position_id = open_initial(account_id, option_symbol=occ)
    idea_id = get_idea_id(sessions, position_id)
    wrong_symbol = f"QQQ   {today:%y%m%d}C00600000"

    with pytest.raises(ValueError, match="underlying mismatch"):
        add(idea_id, option_symbol=wrong_symbol)

    with sessions() as session:
        assert session.get(TradeIdea, idea_id).additions_used == 0


def test_add_after_stop_can_use_new_verified_contract(paper_account):
    account_id, sessions = paper_account
    _, occ = today_and_symbol()
    position_id = open_initial(account_id, option_symbol=occ)
    idea_id = get_idea_id(sessions, position_id)
    assert paper_broker.process_option_stop(position_id, Decimal("0.30"))

    _, replacement_occ = today_and_symbol(605)
    new_id = add(idea_id, option_symbol=replacement_occ, strike=605)
    assert new_id != position_id
    with sessions() as session:
        position = session.get(OptionPosition, new_id)
        assert position.trade_idea_id == idea_id
        assert position.option_symbol == replacement_occ
        assert position.entry_type == "ADD"
        assert session.get(TradeIdea, idea_id).additions_used == 1


def test_second_add_for_same_idea_rejected(paper_account):
    account_id, sessions = paper_account
    _, occ = today_and_symbol()
    position_id = open_initial(account_id, option_symbol=occ)
    idea_id = get_idea_id(sessions, position_id)
    add(idea_id, option_symbol=occ)

    with pytest.raises(ValueError, match="ADD limit"):
        add(idea_id, option_symbol=occ)

    with sessions() as session:
        assert session.get(OptionPosition, position_id).quantity == 3
        assert session.get(TradeIdea, idea_id).additions_used == 1

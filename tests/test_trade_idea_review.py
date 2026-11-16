"""Review correlations are durable, conservative, and never execute."""
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from my_trading_simulator.database.models import (
    Base, ClassificationTradeReview, IncomingNotification,
    NotificationClassification, OptionPosition, PaperAccount, TradeIdea,
)
from my_trading_simulator.database.migrate_trade_idea_reviews import migrate
from my_trading_simulator.execution.trade_idea_review import (
    correlate_classification, save_correlation_review,
)


def setup():
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name != "classification_trade_reviews"])
    assert migrate(engine) is True
    assert migrate(engine) is False
    sessions = sessionmaker(bind=engine)
    with sessions.begin() as s:
        account = PaperAccount(name="paper", initial_balance=Decimal("5000"), cash_balance=Decimal("5000"))
        s.add(account)
        s.flush()
        account_id = account.id
        s.add(IncomingNotification(source="TEST", idempotency_key="review-key", message_text="message"))
        s.flush()
        nid = s.scalar(select(IncomingNotification.id))
        item = NotificationClassification(notification_id=nid, action="BUY", symbol="SPY", option_type="CALL", parser_is_actionable=True, execution_allowed=False, reason="test", model_message_id="x")
        s.add(item)
        s.flush()
        cid = item.id
    return sessions, account_id, cid


def add_idea(session, account_id, symbol="SPY", option_type="CALL", additions_used=0):
    idea = TradeIdea(account_id=account_id, symbol=symbol, option_type=option_type, size_type="NORMAL", initial_allocation=Decimal("400"), initial_risk_limit=Decimal("150"), additions_used=additions_used, status="ACTIVE")
    session.add(idea)
    session.flush()
    return idea.id


def add_position(session, account_id, idea_id):
    p = OptionPosition(account_id=account_id, trade_idea_id=idea_id, symbol="SPY", option_type="CALL", strike_price=Decimal("660"), option_symbol="SPY  261116C00660000", expiration_date=date(2026, 11, 16), quantity=2, remaining_quantity=1, entry_price=Decimal("1"), status="OPEN", entry_type="INITIAL")
    session.add(p)
    session.flush()
    return p.id


def test_buy_is_review_only_and_durable_without_position_creation():
    sessions, aid, cid = setup()
    with sessions.begin() as s:
        review = save_correlation_review(s, classification_id=cid, account_id=aid)
        rid = review.id
        assert review.status == "REVIEW_ONLY"
        assert review.execution_allowed is False
    with sessions.begin() as s:
        review = save_correlation_review(s, classification_id=cid, account_id=aid)
        assert review.id == rid
        assert s.scalar(select(OptionPosition.id)) is None
        assert s.scalar(select(TradeIdea.id)) is None
        assert len(s.scalars(select(ClassificationTradeReview)).all()) == 1


def test_add_links_only_unique_active_idea_even_after_stopped_initial():
    sessions, aid, cid = setup()
    with sessions.begin() as s:
        s.get(NotificationClassification, cid).action = "ADD"
        idea_id = add_idea(s, aid)
    with sessions.begin() as s:
        result = correlate_classification(s, classification_id=cid, account_id=aid)
        assert result.status == "LINKED_REVIEW_ONLY"
        assert result.trade_idea_id == idea_id
        assert result.position_id is None
        review = save_correlation_review(s, classification_id=cid, account_id=aid)
        assert review.trade_idea_id == idea_id
        assert not review.execution_allowed


def test_add_blocks_once_allowance_used():
    sessions, aid, cid = setup()
    with sessions.begin() as s:
        s.get(NotificationClassification, cid).action = "ADD"
        add_idea(s, aid, additions_used=1)
    with sessions() as s:
        assert correlate_classification(s, classification_id=cid, account_id=aid).status == "BLOCKED"


def test_add_blocks_conflicting_strike():
    sessions, aid, cid = setup()
    with sessions.begin() as s:
        item = s.get(NotificationClassification, cid)
        item.action = "ADD"
        item.strike_price = Decimal("661")
        idea_id = add_idea(s, aid)
        add_position(s, aid, idea_id)
    with sessions() as s:
        assert "strike conflicts" in correlate_classification(s, classification_id=cid, account_id=aid).reason


def test_exit_links_unique_matching_position_and_runner():
    sessions, aid, cid = setup()
    with sessions.begin() as s:
        s.get(NotificationClassification, cid).action = "PROFIT_TAKE"
        idea_id = add_idea(s, aid)
        pos_id = add_position(s, aid, idea_id)
    with sessions() as s:
        decision = correlate_classification(s, classification_id=cid, account_id=aid)
        assert decision.status == "LINKED_REVIEW_ONLY"
        assert decision.position_id == pos_id
        assert not decision.execution_allowed


def test_exit_blocks_conflicting_contract_symbol():
    sessions, aid, cid = setup()
    with sessions.begin() as s:
        item = s.get(NotificationClassification, cid)
        item.action = "CLOSE"
        item.contract_symbol = "SPY  261116C00661000"
        idea_id = add_idea(s, aid)
        add_position(s, aid, idea_id)
    with sessions() as s:
        assert correlate_classification(s, classification_id=cid, account_id=aid).status == "BLOCKED"


def test_buy_blocks_open_runner_other_symbol():
    sessions, aid, cid = setup()
    with sessions.begin() as s:
        idea_id = add_idea(s, aid)
        add_position(s, aid, idea_id)
    with sessions() as s:
        assert correlate_classification(s, classification_id=cid, account_id=aid).status == "BLOCKED"


def test_duplicate_active_ideas_are_ambiguous():
    sessions, aid, cid = setup()
    with sessions.begin() as s:
        s.get(NotificationClassification, cid).action = "ADD"
        add_idea(s, aid)
        add_idea(s, aid)
    with sessions() as s:
        assert correlate_classification(s, classification_id=cid, account_id=aid).status == "BLOCKED"


def test_execution_flag_blocks_review():
    sessions, aid, cid = setup()
    with sessions.begin() as s:
        s.get(NotificationClassification, cid).execution_allowed = True
    with sessions() as s:
        assert correlate_classification(s, classification_id=cid, account_id=aid).status == "BLOCKED"

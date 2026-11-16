"""Persist conservative trade-idea correlation reviews, never execute trades.

A review is a historical snapshot, not a current approval. Even a LINKED
review is not permission to paper-trade or route an order.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from my_trading_simulator.database.models import (
    ClassificationTradeReview, NotificationClassification, OptionPosition,
    PaperAccount, TradeIdea,
)


@dataclass(frozen=True)
class CorrelationDecision:
    classification_id: int
    account_id: int
    action: str
    status: str
    reason: str
    trade_idea_id: int | None = None
    position_id: int | None = None
    execution_allowed: bool = False


def correlate_classification(session: Session, *, classification_id: int, account_id: int) -> CorrelationDecision:
    """Conservatively match to an existing idea; do not create positions/ideas."""
    if type(classification_id) is not int or classification_id <= 0:
        raise ValueError("Invalid classification ID")
    if type(account_id) is not int or account_id <= 0:
        raise ValueError("Invalid account ID")

    def blocked(action: str, reason: str) -> CorrelationDecision:
        return CorrelationDecision(classification_id, account_id, action, "BLOCKED", reason)

    item = session.get(NotificationClassification, classification_id)
    if item is None:
        return blocked("UNKNOWN", "Classification missing")
    action = item.action
    if session.get(PaperAccount, account_id) is None:
        return blocked(action, "Account missing")
    if item.execution_allowed or not item.parser_is_actionable:
        return blocked(action, "Classification not eligible for review")
    if item.symbol not in {"SPY", "QQQ", "IWM"} or action not in {"BUY", "ADD", "CLOSE", "PROFIT_TAKE"}:
        return blocked(action, "Unsupported symbol or action")

    positions = session.scalars(select(OptionPosition).where(
        OptionPosition.account_id == account_id,
        OptionPosition.status == "OPEN",
        OptionPosition.remaining_quantity > 0,
    )).all()
    ideas = session.scalars(select(TradeIdea).where(
        TradeIdea.account_id == account_id,
        TradeIdea.status == "ACTIVE",
    )).all()

    if action == "BUY":
        if item.option_type not in {"CALL", "PUT"}:
            return blocked(action, "Missing option direction")
        if positions or ideas:
            return blocked(action, "Account has an open position or active trade idea")
        return CorrelationDecision(classification_id, account_id, action, "REVIEW_ONLY", "New idea needs separate risk and contract checks")

    matching_ideas = [idea for idea in ideas if idea.symbol == item.symbol and
                      (item.option_type is None or idea.option_type == item.option_type)]
    if len(ideas) != 1 or len(matching_ideas) != 1:
        return blocked(action, "No unique matching active trade idea")
    idea = matching_ideas[0]

    if action == "ADD":
        if item.option_type not in {"CALL", "PUT"}:
            return blocked(action, "ADD needs explicit CALL/PUT direction")
        if idea.additions_used != 0:
            return blocked(action, "Trade idea has already used its ADD")
        if any(p.trade_idea_id != idea.id for p in positions):
            return blocked(action, "Another position remains open")
        matching_positions = [p for p in positions if p.trade_idea_id == idea.id]
        if len(matching_positions) > 1:
            return blocked(action, "Ambiguous held position")
        if matching_positions:
            position = matching_positions[0]
            if item.strike_price is not None and item.strike_price != position.strike_price:
                return blocked(action, "ADD strike conflicts with held contract")
            if item.contract_symbol is not None and item.contract_symbol != position.option_symbol:
                return blocked(action, "ADD option symbol conflicts with held contract")
        return CorrelationDecision(classification_id, account_id, action, "LINKED_REVIEW_ONLY",
                                   "ADD needs current eligibility, quote, and risk verification", idea.id,
                                   matching_positions[0].id if matching_positions else None)

    # Exits may never infer a held contract from a matching ticker alone.
    if len(positions) != 1:
        return blocked(action, "No unique open position")
    position = positions[0]
    if position.trade_idea_id != idea.id or position.symbol != item.symbol:
        return blocked(action, "Open position is not linked to matching idea")
    if item.option_type is not None and position.option_type != item.option_type:
        return blocked(action, "Exit direction conflicts with held position")
    if item.strike_price is not None and position.strike_price != item.strike_price:
        return blocked(action, "Exit strike conflicts with held position")
    if item.contract_symbol is not None and position.option_symbol != item.contract_symbol:
        return blocked(action, "Exit option symbol conflicts with held position")
    return CorrelationDecision(classification_id, account_id, action, "LINKED_REVIEW_ONLY",
                               "Exit needs fresh held-contract and quantity verification", idea.id, position.id)


def save_correlation_review(session: Session, *, classification_id: int, account_id: int) -> ClassificationTradeReview:
    """Stage one immutable review. Caller owns the transaction and commit.

    A unique DB constraint prevents duplicate records even across processes.
    Existing reviews are never overwritten or interpreted as fresh checks.
    """
    existing = session.scalar(select(ClassificationTradeReview).where(
        ClassificationTradeReview.classification_id == classification_id,
        ClassificationTradeReview.account_id == account_id,
    ))
    if existing is not None:
        return existing
    decision = correlate_classification(session, classification_id=classification_id, account_id=account_id)
    review = ClassificationTradeReview(
        classification_id=classification_id,
        account_id=account_id,
        action=decision.action,
        status=decision.status,
        reason=decision.reason,
        trade_idea_id=decision.trade_idea_id,
        position_id=decision.position_id,
        execution_allowed=False,
        reviewed_at=datetime.now(timezone.utc),
    )
    session.add(review)
    session.flush()
    return review

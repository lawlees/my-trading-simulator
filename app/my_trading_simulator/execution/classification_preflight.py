"""Read-only preflight for saved classifications; never authorizes execution.

A preflight is advisory only. It does not call Schwab, select contracts,
write SQLite, or invoke the paper broker. No output from this module should
be treated as an order authorization.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from my_trading_simulator.database.models import (
    NotificationClassification, OptionPosition, PaperAccount,
)


@dataclass(frozen=True)
class PreflightResult:
    classification_id: int
    account_id: int
    action: str
    status: str
    reason: str
    execution_allowed: bool = False


def review_classification(
    session: Session,
    *,
    classification_id: int,
    account_id: int,
) -> PreflightResult:
    """Review one persisted classification without changing any state.

    Always fails closed. In particular, an actionable LLM response is not
    authorization, and follow-up actions require verified trade context.
    """
    if type(classification_id) is not int or classification_id <= 0:
        raise ValueError("Invalid classification ID")
    if type(account_id) is not int or account_id <= 0:
        raise ValueError("Invalid account ID")

    item = session.get(NotificationClassification, classification_id)
    if item is None:
        return PreflightResult(classification_id, account_id, "UNKNOWN", "BLOCKED", "Classification missing")
    action = item.action
    account = session.get(PaperAccount, account_id)
    if account is None:
        return PreflightResult(classification_id, account_id, action, "BLOCKED", "Paper account missing")
    if item.execution_allowed:
        # Existing ingestion always sets this false. Do not silently trust
        # a manually modified row or an unrelated future workflow.
        return PreflightResult(classification_id, account_id, action, "BLOCKED", "Unexpected execution authorization flag")
    if not item.parser_is_actionable:
        return PreflightResult(classification_id, account_id, action, "BLOCKED", "Classification is not actionable")
    if action == "IGNORE":
        return PreflightResult(classification_id, account_id, action, "BLOCKED", "Ignored signal")
    if action not in {"BUY", "ADD", "CLOSE", "PROFIT_TAKE"}:
        return PreflightResult(classification_id, account_id, action, "BLOCKED", "Unsupported action")
    if item.symbol not in {"SPY", "QQQ", "IWM"}:
        return PreflightResult(classification_id, account_id, action, "BLOCKED", "Unsupported underlying")

    open_positions = session.scalars(
        select(OptionPosition).where(
            OptionPosition.account_id == account_id,
            OptionPosition.status == "OPEN",
            OptionPosition.remaining_quantity > 0,
        )
    ).all()

    if action == "BUY":
        if item.option_type not in {"CALL", "PUT"}:
            return PreflightResult(classification_id, account_id, action, "BLOCKED", "Missing CALL/PUT direction")
        if open_positions:
            return PreflightResult(classification_id, account_id, action, "BLOCKED", "Another position remains open, including runners")
        return PreflightResult(classification_id, account_id, action, "REVIEW_ONLY", "Entry requires contract validation, quote freshness, risk checks, and explicit activation")

    if action == "ADD":
        return PreflightResult(classification_id, account_id, action, "REVIEW_ONLY", "ADD requires linked trade idea and verified one-ADD allowance")

    if len(open_positions) != 1 or open_positions[0].symbol != item.symbol:
        return PreflightResult(classification_id, account_id, action, "BLOCKED", "No unique matching open position")
    return PreflightResult(classification_id, account_id, action, "REVIEW_ONLY", "Exit requires validated held contract and quantity")

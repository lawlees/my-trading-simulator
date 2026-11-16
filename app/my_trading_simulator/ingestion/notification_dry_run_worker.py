"""Single-notification, opt-in, dry-run-only LLM classifier.

No broker, market-data, positions, account balances, or trade events are written.
No Discord message ID, author ID, or channel ID is fabricated.
"""

import argparse
import re
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from my_trading_simulator.observability.performance import timed
from my_trading_simulator.database.models import (
    IncomingNotification, NotificationClassification,
)
from my_trading_simulator.database.session import SessionLocal, engine
from my_trading_simulator.signals.models import TradingSignal

Parser = Callable[..., TradingSignal]


@dataclass(frozen=True)
class WorkerResult:
    notification_id: int
    status: str
    detail: str


def is_test_message(message_text: str) -> bool:
    # Conservative: never pass an explicitly marked test message to an LLM.
    return bool(re.search(r"\btest\b", message_text, flags=re.IGNORECASE))


@timed("notification_processing_total")
def process_notification(
    notification_id: int,
    *,
    session_factory: sessionmaker = SessionLocal,
    parser: Parser | None = None,
) -> WorkerResult:
    """Process one inbox record once. Requires table migration before invocation.

    A committed PROCESSING claim prevents two concurrent workers from executing
    the same request. Failed/crashed claims require deliberate manual review.
    """
    if notification_id < 1:
        raise ValueError("notification_id must be positive")

    with session_factory() as session:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        item = session.get(IncomingNotification, notification_id)
        if item is None:
            session.rollback()
            return WorkerResult(notification_id, "NOT_FOUND", "No such notification")
        if item.processing_status != "RECEIVED":
            status = item.processing_status
            session.rollback()
            return WorkerResult(notification_id, status, "Not eligible for processing")
        existing = session.scalar(
            select(NotificationClassification.id).where(
                NotificationClassification.notification_id == notification_id
            )
        )
        if existing is not None:
            session.rollback()
            return WorkerResult(notification_id, "ALREADY_CLASSIFIED", "Result already saved")

        text = item.message_text
        if is_test_message(text):
            item.processing_status = "SKIPPED_TEST"
            session.commit()
            return WorkerResult(notification_id, "SKIPPED_TEST", "Test message ignored")

        item.processing_status = "PROCESSING"
        item.processing_error = None
        session.commit()

    # Only local inbox identity is known. This is NOT a Discord message ID.
    local_message_id = f"inbox-{notification_id}"
    try:
        if parser is None:
            # Lazy import allows tests and offline test skips without OpenAI credentials.
            from my_trading_simulator.signals.llm_parser import parse_discord_message
            parser = parse_discord_message
        signal = parser(message_id=local_message_id, message_text=text, context=None)
        if not isinstance(signal, TradingSignal):
            raise TypeError("Parser must return TradingSignal")

        # Although the parser can classify a BUY as actionable, this worker
        # NEVER authorizes execution; context is absent and no trade path exists.
        with session_factory() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            item = session.get(IncomingNotification, notification_id)
            if item is None or item.processing_status != "PROCESSING":
                session.rollback()
                return WorkerResult(notification_id, "CONFLICT", "Claim changed during parsing")
            session.add(NotificationClassification(
                notification_id=notification_id,
                model_message_id=local_message_id,
                action=signal.action.value,
                symbol=signal.symbol,
                option_type=(signal.option_type.value if signal.option_type else None),
                strike_price=signal.strike_price,
                contract_symbol=signal.contract_symbol,
                parser_is_actionable=signal.is_actionable,
                execution_allowed=False,
                reason=signal.reason,
            ))
            item.processing_status = "CLASSIFIED_DRY_RUN"
            session.commit()
        return WorkerResult(notification_id, "CLASSIFIED_DRY_RUN", signal.action.value)
    except Exception as exc:
        # No silent retry. Preserve an error for explicit investigation.
        with session_factory() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            item = session.get(IncomingNotification, notification_id)
            if item is not None and item.processing_status == "PROCESSING":
                item.processing_status = "FAILED_CLASSIFICATION"
                # Do not persist exception details that could contain credentials.
                item.processing_error = f"{type(exc).__name__}; consult local worker logs"
                session.commit()
            else:
                session.rollback()
        raise


def main() -> None:
    cli = argparse.ArgumentParser(description="Classify one inbox message; trading disabled")
    cli.add_argument("--notification-id", type=int, required=True)
    args = cli.parse_args()
    NotificationClassification.__table__.create(bind=engine, checkfirst=True)
    result = process_notification(args.notification_id)
    print(f"Notification #{result.notification_id}: {result.status} ({result.detail})")


if __name__ == "__main__":
    main()

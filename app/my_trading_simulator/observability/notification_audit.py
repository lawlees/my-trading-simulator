"""Read-only notification queue diagnostics for AWS operators.

This command NEVER contacts OpenAI or Schwab, publishes alerts, changes database
state, or retries messages. It deliberately avoids printing message contents,
secrets, or raw authentication headers.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from my_trading_simulator.database.models import (
    IncomingNotification,
    NotificationClassification,
)
from my_trading_simulator.database.session import DATABASE_PATH, SessionLocal


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def summarize_notifications(
    *, session_factory: sessionmaker = SessionLocal,
    now: datetime | None = None,
    processing_timeout_seconds: int = 120,
) -> dict:
    """Return aggregate operational metrics without message text or credentials."""
    if processing_timeout_seconds <= 0:
        raise ValueError("processing_timeout_seconds must be positive")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include a timezone")
    with session_factory() as session:
        totals = dict(session.execute(
            select(IncomingNotification.processing_status, func.count(IncomingNotification.id))
            .group_by(IncomingNotification.processing_status)
        ).all())
        classifications = session.execute(
            select(NotificationClassification.action, func.count(NotificationClassification.id))
            .group_by(NotificationClassification.action)
        ).all()
        pending_rows = session.execute(
            select(IncomingNotification.id, IncomingNotification.received_at)
            .where(IncomingNotification.processing_status == "RECEIVED")
        ).all()
        processing_rows = session.execute(
            select(IncomingNotification.id, IncomingNotification.received_at)
            .where(IncomingNotification.processing_status == "PROCESSING")
        ).all()
        unauthorized_classifications = session.scalar(
            select(func.count(NotificationClassification.id))
            .where(NotificationClassification.execution_allowed.is_(True))
        ) or 0
    pending_ids = [id_ for id_, _ in pending_rows]
    stuck_ids = [id_ for id_, received in processing_rows
                 if (now - _utc(received)).total_seconds() > processing_timeout_seconds]
    return {
        "notification_statuses": totals,
        "classification_actions": dict(classifications),
        "pending_received_ids": sorted(pending_ids),
        "possible_stuck_processing_ids": sorted(stuck_ids),
        "execution_authorized_classifications": int(unauthorized_classifications),
        "read_only": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only trading notification audit")
    parser.add_argument("--processing-timeout-seconds", type=int, default=120)
    args = parser.parse_args(argv)
    # Do not create an empty SQLite database if the path was misconfigured.
    if not Path(DATABASE_PATH).is_file():
        parser.error("Application database not found; nothing was changed")
    report = summarize_notifications(processing_timeout_seconds=args.processing_timeout_seconds)
    print(json.dumps(report, sort_keys=True, indent=2))
    return 1 if report["execution_authorized_classifications"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

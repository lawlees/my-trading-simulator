
"""Persistent dry-run-only notification classification worker.

Safety guarantees:
- No brokerage access or trade execution.
- Uses the existing single-notification dry-run classifier.
- Processes only notifications created after worker startup.
- Rejects notifications older than the configured age limit.
- Processes notifications in database ID order.
- Never automatically retries failed classifications.
- Prevents concurrent worker processes on the same host.
- Supports graceful SIGTERM and SIGINT shutdown.
"""

import argparse
import logging
import signal
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select

from my_trading_simulator.database.models import (
    IncomingNotification,
)
from my_trading_simulator.database.session import SessionLocal
from my_trading_simulator.ingestion.notification_dry_run_worker import (
    process_notification,
)
from my_trading_simulator.market_data.schwab_worker_lock import (
    SchwabWorkerLock,
)

logger = logging.getLogger(__name__)

DEFAULT_POLL_SECONDS = 0.5
DEFAULT_MAX_AGE_SECONDS = 120

# Locate the project root from this module rather than
# hardcoding the AWS or Mac home directory.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CLASSIFIER_LOCK_PATH = (
    PROJECT_ROOT / "data" / "classification-worker.lock"
)


def get_startup_watermark(
    *,
    session_factory=SessionLocal,
) -> int:
    """Return the highest notification ID existing at startup.

    A persistent worker must not automatically process messages
    received while the service was stopped.
    """
    with session_factory() as session:
        maximum_id = session.scalar(
            select(func.max(IncomingNotification.id))
        )

    return int(maximum_id or 0)


def get_next_notification_id(
    *,
    max_age_seconds=DEFAULT_MAX_AGE_SECONDS,
    min_notification_id=0,
    session_factory=SessionLocal,
):
    """Find the oldest eligible notification.

    Only notifications newer than the startup watermark
    and within the permitted age window are eligible.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=max_age_seconds
    )

    with session_factory() as session:
        return session.scalar(
            select(IncomingNotification.id)
            .where(
                IncomingNotification.processing_status == "RECEIVED",
                IncomingNotification.id > min_notification_id,
                IncomingNotification.received_at >= cutoff,
            )
            .order_by(IncomingNotification.id.asc())
            .limit(1)
        )


def mark_unclaimed_failure(
    notification_id,
    *,
    session_factory=SessionLocal,
):
    """Fail closed if a processor unexpectedly raises before claiming.

    The normal classifier already records failures after
    claiming a notification. This is a defensive fallback.

    Never overwrite a notification that is already processing,
    completed, skipped, or failed.
    """
    with session_factory() as session:
        session.connection().exec_driver_sql(
            "BEGIN IMMEDIATE"
        )

        item = session.get(
            IncomingNotification,
            notification_id,
        )

        if (
            item is not None
            and item.processing_status == "RECEIVED"
        ):
            item.processing_status = "FAILED_CLASSIFICATION"
            item.processing_error = (
                "UnexpectedWorkerError; "
                "consult local worker logs"
            )
            session.commit()
        else:
            session.rollback()


def process_next_notification(
    *,
    max_age_seconds=DEFAULT_MAX_AGE_SECONDS,
    min_notification_id=0,
    session_factory=SessionLocal,
    processor=process_notification,
):
    """Process at most one eligible notification.

    All trading authorization remains disabled in the
    underlying dry-run classifier.
    """
    notification_id = get_next_notification_id(
        max_age_seconds=max_age_seconds,
        min_notification_id=min_notification_id,
        session_factory=session_factory,
    )

    if notification_id is None:
        return None

    try:
        result = processor(notification_id)

        logger.info(
            "classification notification_id=%s status=%s",
            result.notification_id,
            result.status,
        )

        return result

    except Exception:
        # Do not log exception text, notification contents,
        # credentials, or other potentially sensitive data.
        logger.error(
            "classification failed notification_id=%s",
            notification_id,
        )

        # If the processor failed before it could claim the
        # record, mark it failed rather than retrying forever.
        # A database failure here is fatal and stops the worker.
        mark_unclaimed_failure(
            notification_id,
            session_factory=session_factory,
        )

        return None


def run_forever(
    *,
    poll_seconds=DEFAULT_POLL_SECONDS,
    max_age_seconds=DEFAULT_MAX_AGE_SECONDS,
    stop_event=None,
    session_factory=SessionLocal,
):
    """Poll until shutdown, ignoring the pre-startup backlog."""
    if poll_seconds <= 0:
        raise ValueError(
            "poll_seconds must be positive"
        )

    if max_age_seconds <= 0:
        raise ValueError(
            "max_age_seconds must be positive"
        )

    if stop_event is None:
        stop_event = threading.Event()

    # Capture the database's highest ID exactly once.
    # A restart establishes a new watermark.
    startup_watermark = get_startup_watermark(
        session_factory=session_factory,
    )

    logger.info(
        "Dry-run classifier started; startup_watermark=%s",
        startup_watermark,
    )

    while not stop_event.is_set():
        process_next_notification(
            max_age_seconds=max_age_seconds,
            min_notification_id=startup_watermark,
            session_factory=session_factory,
        )

        stop_event.wait(poll_seconds)

    logger.info(
        "Persistent dry-run classifier stopped"
    )


def main():
    """Start one locked, persistent dry-run classifier."""
    parser = argparse.ArgumentParser(
        description=(
            "Persistent dry-run notification classifier; "
            "brokerage execution disabled"
        )
    )

    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=DEFAULT_POLL_SECONDS,
    )

    parser.add_argument(
        "--max-age-seconds",
        type=int,
        default=DEFAULT_MAX_AGE_SECONDS,
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    stop_event = threading.Event()

    def request_shutdown(signum, frame):
        stop_event.set()

    signal.signal(
        signal.SIGTERM,
        request_shutdown,
    )
    signal.signal(
        signal.SIGINT,
        request_shutdown,
    )

    CLASSIFIER_LOCK_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # This lock is separate from the Schwab worker lock.
    with SchwabWorkerLock(CLASSIFIER_LOCK_PATH):
        run_forever(
            poll_seconds=args.poll_seconds,
            max_age_seconds=args.max_age_seconds,
            stop_event=stop_event,
        )


if __name__ == "__main__":
    main()

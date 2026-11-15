"""Paper-only Discord outbox worker.

Publishes committed trade_events; never executes trades or calls Schwab.
Nothing runs on import. One batch is bounded; continuous polling is opt-in.
FAILED, UNKNOWN, and stranded SENDING items require reconciliation and are
NOT automatically retried by this worker.
"""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv

from my_trading_simulator.observability.performance import timed
from my_trading_simulator.discord.discord_outbox_publisher import (
    PublishResult,
    publish_one_pending_event,
)

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class BatchResult:
    outcomes: tuple[PublishResult, ...]
    queue_empty: bool

    @property
    def sent(self) -> int:
        return sum(x.status == "SENT" for x in self.outcomes)

    @property
    def attention_required(self) -> int:
        return sum(x.status in {"FAILED", "UNKNOWN"} for x in self.outcomes)


@timed("discord_publish_batch")
def publish_pending_batch(
    *,
    max_events: int = 20,
    publisher: Callable[[], PublishResult] = publish_one_pending_event,
) -> BatchResult:
    """Try at most max_events *different* pending events, stopping at EMPTY.

    The publisher commits a claim before sending and will not select the same
    event again if delivery fails. The batch itself never performs retries.
    """
    if type(max_events) is not int or not 1 <= max_events <= 100:
        raise ValueError("max_events must be an integer between 1 and 100")

    results: list[PublishResult] = []
    seen_ids: set[int] = set()
    for _ in range(max_events):
        outcome = publisher()
        if not isinstance(outcome, PublishResult):
            raise TypeError("publisher returned an unexpected result")
        if outcome.status == "EMPTY":
            return BatchResult(tuple(results), queue_empty=True)
        if outcome.status not in {"SENT", "FAILED", "UNKNOWN"}:
            raise RuntimeError(f"Unexpected publisher status: {outcome.status}")
        if type(outcome.event_id) is not int or outcome.event_id in seen_ids:
            raise RuntimeError("Publisher returned a missing or repeated event ID")
        seen_ids.add(outcome.event_id)
        results.append(outcome)
        if outcome.status != "SENT":
            LOGGER.warning("Event %s requires delivery review: %s", outcome.event_id, outcome.status)
    return BatchResult(tuple(results), queue_empty=False)


def run_continuously(
    *,
    poll_seconds: float = 5.0,
    max_events: int = 20,
    publisher: Callable[[], PublishResult] = publish_one_pending_event,
    stop_event=None,
) -> None:
    """Explicitly started polling loop. A stop_event supports clean shutdown.

    Failures in one cycle are logged without ever re-executing a trade.
    Manual review is required for UNKNOWN and stranded SENDING entries.
    """
    if not isinstance(poll_seconds, (int, float)) or isinstance(poll_seconds, bool) or not 1 <= poll_seconds <= 3600:
        raise ValueError("poll_seconds must be between 1 and 3600")
    if type(max_events) is not int or not 1 <= max_events <= 100:
        raise ValueError("max_events must be between 1 and 100")
    while stop_event is None or not stop_event.is_set():
        try:
            result = publish_pending_batch(max_events=max_events, publisher=publisher)
            if result.outcomes:
                LOGGER.info("Discord batch: %s sent, %s require review", result.sent, result.attention_required)
        except Exception:
            # Do not log exception details: a third-party HTTP failure could
            # expose a webhook URL through its exception string.
            LOGGER.error("Discord publisher cycle failed; investigate configuration and delivery state")
        if stop_event is not None:
            if stop_event.wait(poll_seconds):
                break
        else:
            time.sleep(poll_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Paper-only SQLite-to-Discord publisher")
    parser.add_argument("--continuous", action="store_true", help="Run until interrupted; default is one bounded batch")
    parser.add_argument("--interval", type=float, default=5.0, help="Seconds between batches in continuous mode")
    parser.add_argument("--batch-size", type=int, default=20, help="Max events per batch (1–100)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Explicit path avoids python-dotenv's stdin / notebook stack inspection bug.
    load_dotenv(dotenv_path=Path.cwd() / ".env")
    if args.continuous:
        LOGGER.info("Starting paper-only Discord publisher (Ctrl+C to stop)")
        try:
            run_continuously(poll_seconds=args.interval, max_events=args.batch_size)
        except KeyboardInterrupt:
            LOGGER.info("Discord publisher stopped")
    else:
        result = publish_pending_batch(max_events=args.batch_size)
        print(f"Batch complete: sent={result.sent}, review={result.attention_required}, empty={result.queue_empty}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

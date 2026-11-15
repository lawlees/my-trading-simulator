"""One-cycle coordinator for paper-only option stop monitoring.

No loop starts on import. No Schwab client or Discord sender is created here.
The caller supplies a read-only quote client and invokes run_monitor_cycle().
A persistent outbox and market calendar are required before unattended use.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from my_trading_simulator.observability.performance import timed
from my_trading_simulator.database.models import OptionPosition
from my_trading_simulator.database.session import SessionLocal
from my_trading_simulator.execution.stop_monitor import (
    StopCheckResult,
    monitor_position_once,
)


@dataclass(frozen=True)
class MonitorCycleResult:
    checked: int
    results: tuple[StopCheckResult, ...]

    @property
    def alerts(self) -> tuple[StopCheckResult, ...]:
        return tuple(item for item in self.results if item.status == "ALERT")


@timed("paper_stop_monitor_cycle")
def run_monitor_cycle(
    quote_client,
    *,
    session_factory=None,
    now: datetime | None = None,
    stop_executor=None,
) -> MonitorCycleResult:
    """Check every currently open position once.

    Fetch position IDs in a short read transaction. Each check independently
    re-reads the position; concurrent closes are handled by monitor_position_once.
    Failures for one position do not stop checks for the other positions.

    Returns results in memory; it does NOT yet persist alerts or send Discord
    messages. Do not use as an unattended service until those are implemented.
    """
    sessions = session_factory or SessionLocal
    with sessions() as session:
        position_ids = tuple(session.scalars(
            select(OptionPosition.id)
            .where(
                OptionPosition.status == "OPEN",
                OptionPosition.remaining_quantity > 0,
            )
            .order_by(OptionPosition.id)
        ).all())

    results = []
    for position_id in position_ids:
        try:
            result = monitor_position_once(
                position_id,
                quote_client,
                session_factory=sessions,
                now=now,
                stop_executor=stop_executor,
            )
        except Exception as exc:
            # Fail safe: never manufacture a quote or execute a simulated sell.
            # Caller must surface these alerts; not safe to silently ignore.
            result = StopCheckResult(
                position_id,
                "ALERT",
                f"Unexpected monitor failure: {type(exc).__name__}",
            )
        results.append(result)

    return MonitorCycleResult(len(position_ids), tuple(results))

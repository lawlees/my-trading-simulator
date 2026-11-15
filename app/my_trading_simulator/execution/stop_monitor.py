"""One-pass, paper-only monitoring of a persisted long-option stop.

Does not run automatically. Caller must schedule polling and error alerts.
Never submits brokerage orders, and never fabricates prices.
"""
from dataclasses import dataclass
from datetime import datetime, time, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from my_trading_simulator.database.models import OptionPosition
from my_trading_simulator.database.session import SessionLocal
from my_trading_simulator.execution import paper_broker
from my_trading_simulator.market_data.held_option_quote import validated_held_option_bid

EASTERN = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class StopCheckResult:
    position_id: int
    status: str
    reason: str
    bid: Decimal | None = None


def _regular_session(now: datetime) -> bool:
    """Time-of-day guard, NOT a holiday/early-close market calendar."""
    local = now.astimezone(EASTERN)
    return local.weekday() < 5 and time(9, 30) <= local.time() < time(16, 0)


def monitor_position_once(
    position_id: int,
    quote_client,
    *,
    now: datetime | None = None,
    session_factory=None,
    stop_executor=None,
) -> StopCheckResult:
    """Read an open position, validate a Schwab quote, then simulate a stop.

    `quote_client` implements get_option_quote(exact_occ_symbol).
    No API call happens on module import. `stop_executor` defaults to the
    transactional paper_broker.process_option_stop function.

    `now` is a deterministic clock override intended for tests. In production
    omit it so quote freshness is assessed after the network response arrives.
    """
    if type(position_id) is not int or position_id <= 0:
        raise ValueError("position_id must be a positive integer")
    if now is not None and (not isinstance(now, datetime) or now.tzinfo is None):
        raise ValueError("now must be timezone-aware")

    sessions = session_factory or SessionLocal
    execute_stop = stop_executor or paper_broker.process_option_stop

    with sessions() as session:
        position = session.get(OptionPosition, position_id)
        if position is None or position.status != "OPEN" or position.remaining_quantity <= 0:
            return StopCheckResult(position_id, "SKIPPED", "Position not open")
        if not isinstance(position.option_symbol, str) or not position.option_symbol.strip():
            return StopCheckResult(position_id, "ALERT", "Missing verified option symbol")
        # Keep a detached snapshot: no DB transaction remains open during network I/O.
        from types import SimpleNamespace
        snapshot = SimpleNamespace(
            option_symbol=position.option_symbol,
            symbol=position.symbol,
            option_type=position.option_type,
            expiration_date=position.expiration_date,
            strike_price=position.strike_price,
            status=position.status,
            remaining_quantity=position.remaining_quantity,
        )

    observation_time = now or datetime.now(timezone.utc)
    if not _regular_session(observation_time):
        return StopCheckResult(position_id, "SKIPPED", "Outside regular session time")

    try:
        response = quote_client.get_option_quote(snapshot.option_symbol)
    except Exception as exc:
        return StopCheckResult(position_id, "ALERT", f"Quote request failed: {type(exc).__name__}")

    # Capture clock AFTER network I/O. Injected `now` is for deterministic tests.
    observation_time = now or datetime.now(timezone.utc)
    if not _regular_session(observation_time):
        return StopCheckResult(position_id, "SKIPPED", "Outside regular session time")

    bid, reason = validated_held_option_bid(snapshot, response, now=observation_time)
    if bid is None:
        return StopCheckResult(position_id, "ALERT", reason)

    try:
        closed = execute_stop(position_id, bid)
    except Exception as exc:
        return StopCheckResult(position_id, "ALERT", f"Paper stop processing failed: {type(exc).__name__}", bid)

    if closed:
        return StopCheckResult(position_id, "STOP_FILLED", "Paper stop filled and committed", bid)
    return StopCheckResult(position_id, "NO_EXIT", "Stop not triggered or position changed", bid)

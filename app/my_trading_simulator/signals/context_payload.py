
import json
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal

from my_trading_simulator.signals.snapshot import (
    TradingContextSnapshot,
)


def _serialize_value(value):
    """
    Convert Python values into JSON-compatible values.
    """
    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    raise TypeError(
        f"Cannot serialize value of type {type(value).__name__}"
    )


def build_context_payload(
    snapshot: TradingContextSnapshot,
) -> str:
    """
    Serialize a trading context snapshot for the LLM.

    The LLM receives context for interpretation only.
    Execution authorization remains outside the LLM.
    """
    payload = {
        "context_is_valid": snapshot.context_is_valid,
        "open_position_count": snapshot.open_position_count,
        "active_trade_idea_count": (
            snapshot.active_trade_idea_count
        ),
        "active_position": (
            asdict(snapshot.active_position)
            if snapshot.active_position is not None
            else None
        ),
        "active_trade_idea": (
            asdict(snapshot.active_trade_idea)
            if snapshot.active_trade_idea is not None
            else None
        ),
        "recent_messages": [
            asdict(message)
            for message in snapshot.recent_messages
        ],
    }

    return json.dumps(
        payload,
        default=_serialize_value,
        indent=2,
    )

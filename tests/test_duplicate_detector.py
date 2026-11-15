
from datetime import datetime, timedelta, timezone

import pytest

from my_trading_simulator.ingestion.duplicate_detector import (
    NotificationIdentity,
    classify_duplicate,
    normalize_message,
)


NOW = datetime(2026, 11, 14, 15, 0, tzinfo=timezone.utc)


def notification(
    source: str,
    text: str,
    seconds_later: int = 0,
    message_id: str | None = None,
) -> NotificationIdentity:
    return NotificationIdentity(
        source=source,
        message_text=text,
        received_at=NOW + timedelta(seconds=seconds_later),
        source_message_id=message_id,
    )


def test_normalize_message():
    assert normalize_message("  SPY   CALLS \n HERE  ") == "spy calls here"


def test_same_message_id_is_exact_duplicate():
    previous = notification(
        "IPHONE_NOTIFICATION", "SPY calls",
        message_id="123456789",
    )
    incoming = notification(
        "MANUAL_DISCORD", "Forwarded: SPY calls",
        seconds_later=120,
        message_id="123456789",
    )

    assert classify_duplicate(incoming, [previous]) == "EXACT_DUPLICATE"


def test_same_text_from_two_sources_is_possible_duplicate():
    previous = notification(
        "IPHONE_NOTIFICATION", "SPY calls here",
    )
    incoming = notification(
        "MANUAL_DISCORD", " SPY  CALLS here ",
        seconds_later=20,
    )

    assert classify_duplicate(incoming, [previous]) == "POSSIBLE_DUPLICATE"


def test_different_text_is_new():
    previous = notification("IPHONE_NOTIFICATION", "SPY calls")
    incoming = notification(
        "MANUAL_DISCORD", "QQQ puts",
        seconds_later=10,
    )

    assert classify_duplicate(incoming, [previous]) == "NEW"


def test_same_text_outside_window_is_new():
    previous = notification("IPHONE_NOTIFICATION", "SPY calls")
    incoming = notification(
        "MANUAL_DISCORD", "SPY calls",
        seconds_later=1200,
    )

    assert classify_duplicate(incoming, [previous]) == "NEW"


def test_exact_id_takes_priority_over_text():
    previous = notification(
        "MANUAL_DISCORD", "Original content",
        message_id="888888",
    )
    incoming = notification(
        "IPHONE_NOTIFICATION", "Truncated content",
        seconds_later=300,
        message_id="888888",
    )

    assert classify_duplicate(incoming, [previous]) == "EXACT_DUPLICATE"


def test_no_prior_messages_is_new():
    incoming = notification("IPHONE_NOTIFICATION", "SPY calls")
    assert classify_duplicate(incoming, []) == "NEW"


def test_naive_timestamp_is_rejected():
    incoming = NotificationIdentity(
        source="IPHONE_NOTIFICATION",
        message_text="SPY calls",
        received_at=datetime(2026, 11, 14, 15, 0),
    )

    with pytest.raises(ValueError):
        classify_duplicate(incoming, [])


def test_invalid_window_is_rejected():
    incoming = notification("IPHONE_NOTIFICATION", "SPY calls")

    with pytest.raises(ValueError):
        classify_duplicate(incoming, [], window_seconds=-1)

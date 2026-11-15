
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal


DuplicateStatus = Literal[
    "NEW",
    "EXACT_DUPLICATE",
    "POSSIBLE_DUPLICATE",
]


@dataclass(frozen=True)
class NotificationIdentity:
    source: str
    message_text: str
    received_at: datetime
    source_message_id: str | None = None


def normalize_message(text: str) -> str:
    """Normalize whitespace and case without changing message meaning."""
    return re.sub(r"\s+", " ", text).strip().casefold()


def to_utc(value: datetime) -> datetime:
    """Require timezone-aware timestamps for comparisons."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("received_at must be timezone-aware")
    return value.astimezone(timezone.utc)


def classify_duplicate(
    incoming: NotificationIdentity,
    existing: list[NotificationIdentity],
    window_seconds: int = 60,
) -> DuplicateStatus:
    """
    Classify an incoming notification against existing notifications.

    Matching message IDs are authoritative only when they are verified
    original Discord IDs within the same identity namespace.

    Matching text alone is never considered an exact duplicate.

    This function does not execute trades.
    """
    if window_seconds < 0:
        raise ValueError("window_seconds must be nonnegative")

    incoming_time = to_utc(incoming.received_at)
    incoming_text = normalize_message(incoming.message_text)

    possible_duplicate = False

    for previous in existing:
        previous_time = to_utc(previous.received_at)

        if (
            incoming.source_message_id
            and previous.source_message_id
            and incoming.source_message_id == previous.source_message_id
        ):
            return "EXACT_DUPLICATE"

        time_difference = abs(incoming_time - previous_time)

        if time_difference > timedelta(seconds=window_seconds):
            continue

        if incoming_text and incoming_text == normalize_message(
            previous.message_text
        ):
            possible_duplicate = True

    if possible_duplicate:
        return "POSSIBLE_DUPLICATE"

    return "NEW"

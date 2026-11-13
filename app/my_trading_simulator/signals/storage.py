
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from my_trading_simulator.database.models import DiscordMessage


def save_discord_message(
    session: Session,
    message_id: str,
    author_id: str,
    channel_id: str,
    message_text: str,
    message_timestamp: datetime,
) -> bool:
    """
    Stage a Discord message in the caller's transaction.

    Returns True for a new message.
    Returns False for an existing message.

    The caller must commit the transaction.
    The database unique constraint provides final
    duplicate protection.
    """
    if not message_id.strip():
        raise ValueError("message_id cannot be empty")

    if message_timestamp.tzinfo is None:
        raise ValueError(
            "message_timestamp must be timezone-aware"
        )

    existing = session.scalar(
        select(DiscordMessage.id).where(
            DiscordMessage.discord_message_id == message_id
        )
    )

    if existing is not None:
        return False

    message = DiscordMessage(
        discord_message_id=message_id,
        author_id=author_id,
        channel_id=channel_id,
        message_text=message_text,
        message_timestamp=message_timestamp,
        processing_status="RECEIVED",
    )

    session.add(message)
    session.flush()

    return True
